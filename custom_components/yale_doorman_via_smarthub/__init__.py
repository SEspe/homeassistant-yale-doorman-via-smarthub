import asyncio
from datetime import datetime, timedelta, timezone
import logging
import os
import json

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.translation import async_get_translations
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.json import load_json
from homeassistant.util import dt as dt_util

from .api import YaleAuthError, YaleDoormanViaSmarthubApiClient

from .const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_ENABLE_BINARY_SENSOR,
    DOMAIN,
    PLATFORMS,
    LOCK,
    BINARY_SENSOR,
    EVENT,
    ACTIVITY_EVENT_TYPES,
    LOG_FETCH_RETRIES,
    LOG_SAFETY_POLLS,
    STARTUP_MESSAGE,
)

SCAN_INTERVAL = timedelta(seconds=30)
# Upper bound for pages: "*" in the download_yale_event_log service
MAX_LOG_PAGES = 50

_LOGGER: logging.Logger = logging.getLogger(__package__)

async def async_setup(hass: HomeAssistant, config: ConfigType):
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    if hass.data.get(DOMAIN) is None:
        hass.data.setdefault(DOMAIN, {})
        _LOGGER.info(STARTUP_MESSAGE)
    
    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)
    enable_binary_sensor = entry.data.get(CONF_ENABLE_BINARY_SENSOR, True)
    
    session = async_get_clientsession(hass)
    client = YaleDoormanViaSmarthubApiClient(hass, username, password, session)
    
    coordinator = YaleDoormanViaSmarthubDataUpdateCoordinator(hass, entry, client=client)
    # Raises ConfigEntryNotReady (retry later) on failure, or ConfigEntryAuthFailed when
    # Yale rejects the password - HA then asks the user for a new one (reauth flow).
    await coordinator.async_config_entry_first_refresh()
    
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    coordinator.platforms.append(LOCK)
    if enable_binary_sensor:
        coordinator.platforms.append(BINARY_SENSOR)
    coordinator.platforms.append(EVENT)
    await hass.config_entries.async_forward_entry_setups(entry, coordinator.platforms)
    
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    
    async def handle_download_log(call: ServiceCall) -> dict:
        """Handles the service action to download the event log."""
        _LOGGER.info("Calling service action to download Yale event log")

        try:
            coordinator: YaleDoormanViaSmarthubDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
            
            device_map = {} # Will store (area, zone) -> "Name"
            
            try:
                # Get device list from coordinator data (like in entity.py)
                device_list = coordinator.data.get("data", {}).get("device_status", [])
                for device in device_list:
                    try:
                        area = int(device.get("area"))
                        zone = int(device.get("no"))
                        name = device.get("name")
                        if area is not None and zone is not None and name:
                            device_map[(area, zone)] = name
                    except (TypeError, ValueError):
                        continue

                _LOGGER.debug(f"Built device map: {device_map}")
            except Exception as e:
                _LOGGER.error(f"Failed to build device map from coordinator data: {e}")

            # Get page count from service call
            pages = str(call.data.get("pages", 1)).strip()
            max_pages = MAX_LOG_PAGES if pages == "*" else int(pages)
            utc = bool(call.data.get("utc", False))
            all_events = []
            pages_fetched = 0

            for page_num in range(1, max_pages + 1):
                log_data = await coordinator.api.async_get_yale_event_log(page_number=str(page_num), utc=utc)
                log_events = (log_data or {}).get("data") or []
                _LOGGER.info(f"Downloaded page {str(page_num)} with {len(log_events)} events")
                if not log_events:
                    break  # past the last page
                pages_fetched = page_num
                all_events.extend(log_events)

            language = hass.config.language or "en"

            # Event texts per language - kept out of translations/, where hassfest only
            # allows Home Assistant's own sections
            path = os.path.join(os.path.dirname(__file__), "event_log_texts.json")

            def _load_event_texts():
                # Off-loop file read - blocking I/O on the event loop is trapped by HA.
                with open(path, encoding="utf-8") as f:
                    return json.load(f)

            event_texts = await hass.async_add_executor_job(_load_event_texts)
            
            event_type_map = event_texts.get(language) or event_texts["en"]

            formatted_events = []
            for event in all_events:
                event_id = str(event.get("event_type"))
                event_area = event.get("area")
                event_zone = event.get("zone")
                device_key = None
                device_name = "System"

                try:
                    area_int = int(event_area)
                    zone_int = int(event_zone)

                    if area_int > 0:
                        device_key = (area_int, zone_int)
                        device_name = device_map.get(
                            device_key,
                            f"Unknown Device (A:{area_int}, Z:{zone_int})"
                        )
                except (TypeError, ValueError):
                    pass

                translated_event = event_type_map.get(event_id, f"Unknown event {event_id}")

                try:
                    event_id_int = int(event_id)
                except ValueError:
                    event_id_int = None

                if (event_id_int is not None and 1301 <= event_id_int <= 1398) or event_id in ["1602"]:
                    formatted_events.append({
                        "Time": event.get("time", "N/A"),
                        "Event": translated_event,
                    })
                elif event_id in ["1801", "1807", "1815", "1816", "3801", "3802"]:
                    formatted_events.append({
                        "Time": event.get("time", "N/A"),
                        "Event": translated_event,
                        "Device": device_name,
                    })
                else:
                    formatted_events.append({
                        "Time": event.get("time", "N/A"),
                        "Event": translated_event,
                        "Device": device_name,
                        "Name": event.get("name", ""),
                    })

            return {
                "event_log_table": formatted_events,
                "total_rows_returned": len(formatted_events),
                "pages_fetched": pages_fetched
#                "log_data": log_data
            }

        except Exception as e:
            _LOGGER.error(f"Could not download Yale event log: {e}")
            raise

    hass.services.async_register(
        DOMAIN, 
        "download_yale_event_log", 
        handle_download_log,
        supports_response=SupportsResponse.ONLY
    )
#end
    return True

class YaleDoormanViaSmarthubDataUpdateCoordinator(DataUpdateCoordinator):
    
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: YaleDoormanViaSmarthubApiClient) -> None:
        self.api = client
        self.platforms = []
        # Lock activity read from the Yale event log, oldest first. Each item has an
        # increasing "seq" so event entities can tell which ones they already fired.
        self.activity_events = []
        self.activity_seq = 0
        self._seen_log_keys = None  # None until the first log read sets the baseline
        self._last_lock_status = None
        self._log_fetches_pending = 0
        self._polls_since_log_read = 0
        
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL
        )

    async def _async_update_data(self):
        try:
            status = await self.api.async_status()
            if status is None:
                _LOGGER.warning(
                    "Received no data from Yale smarthub - see preceding log lines "
                    "for the underlying cause (login/auth/network). Marking data as unavailable."
                )
                raise UpdateFailed("No data returned from Yale smarthub")
            device_count = len(status.get("data", {}).get("device_status", []))
            _LOGGER.debug("Coordinator update succeeded, %s device(s) reported", device_count)
        except UpdateFailed:
            raise
        except YaleAuthError as exception:
            # Stops polling and starts HA's reauth flow instead of retrying a bad password
            raise ConfigEntryAuthFailed(
                "Yale rejected the username/password - enter the new password"
            ) from exception
        except Exception as exception:
            _LOGGER.error("Coordinator update failed: %s", exception, exc_info=True)
            raise UpdateFailed(str(exception)) from exception

        try:
            await self._async_update_activity(status)
        except Exception as exception:
            # Activity is a bonus - never let it take the lock/door entities down
            _LOGGER.error("Failed to update lock activity: %s", exception, exc_info=True)
        return status

    async def _async_update_activity(self, status: dict) -> None:
        """Read the Yale event log sparingly, to limit cloud traffic.

        The log is read once at startup to learn which events are old, then right after
        a lock/door status change (for a few polls, since Yale may log the event a little
        after the status flips), plus every LOG_SAFETY_POLLS polls to catch activity
        that left the status unchanged between two polls.
        """
        lock_status = tuple(
            device.get("minigw_lock_status")
            for device in status.get("data", {}).get("device_status", [])
        )
        if self._seen_log_keys is None or (
            self._last_lock_status is not None and lock_status != self._last_lock_status
        ):
            self._log_fetches_pending = LOG_FETCH_RETRIES
        self._last_lock_status = lock_status

        self._polls_since_log_read += 1
        safety_read = LOG_SAFETY_POLLS > 0 and self._polls_since_log_read >= LOG_SAFETY_POLLS
        if self._log_fetches_pending <= 0 and not safety_read:
            return
        self._log_fetches_pending = max(self._log_fetches_pending - 1, 0)
        self._polls_since_log_read = 0

        log_data = await self.api.async_get_yale_event_log(page_number="1", utc=True)
        events = (log_data or {}).get("data")
        if not isinstance(events, list):
            _LOGGER.debug("Event log read returned no events: %s", log_data)
            return

        keys = {self._log_key(event) for event in events}
        if self._seen_log_keys is None:
            _LOGGER.debug("Event log baseline set from %s event(s)", len(events))
            self._seen_log_keys = keys
            self._log_fetches_pending = 0
            return

        new_events = [
            event for event in events
            if self._log_key(event) not in self._seen_log_keys
            and str(event.get("event_type")) in ACTIVITY_EVENT_TYPES
        ]
        # Events that dropped off page 1 can never come back, so only the current page
        # needs remembering
        self._seen_log_keys = keys
        if not new_events:
            _LOGGER.debug("No new lock activity in event log yet")
            return

        self._log_fetches_pending = 0
        for event in reversed(new_events):  # the log is newest first
            try:
                area = int(event.get("area"))
                zone = int(event.get("zone"))
            except (TypeError, ValueError):
                continue
            code = str(event.get("event_type"))
            self.activity_seq += 1
            self.activity_events.append({
                "seq": self.activity_seq,
                "area": area,
                "zone": zone,
                "event_type": ACTIVITY_EVENT_TYPES[code],
                "yale_event_code": code,
                "user": event.get("name") or None,
                "yale_time": self._parse_yale_time(event.get("time")),
            })
            _LOGGER.debug("New lock activity: %s", self.activity_events[-1])
        self.activity_events = self.activity_events[-20:]

    @staticmethod
    def _log_key(event: dict) -> tuple:
        return (
            event.get("time"),
            str(event.get("event_type")),
            event.get("area"),
            event.get("zone"),
            event.get("name"),
        )

    @staticmethod
    def _parse_yale_time(value):
        """Convert Yale's UTC time ("2026/10/11 10:19:49", set_utc=1) to HA local time.

        UTC is requested because set_utc=0 (hub local time) was an hour behind real
        local time on a Norwegian install in summer time.
        """
        try:
            naive = datetime.strptime(value, "%Y/%m/%d %H:%M:%S")
        except (TypeError, ValueError):
            return value
        return dt_util.as_local(naive.replace(tzinfo=timezone.utc)).isoformat()
    
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    unloaded = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
                if platform in coordinator.platforms
            ]
        )
    )
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unloaded

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    # Let HA do the reload - it also dedups with the reload a finished reauth schedules
    hass.config_entries.async_schedule_reload(entry.entry_id)