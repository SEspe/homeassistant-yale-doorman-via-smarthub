from homeassistant.components.event import EventEntity
from homeassistant.core import callback

from .const import (
    DOMAIN,
    ACTIVITY_EVENT_TYPES,
)

from .entity import YaleDoormanViaSmarthubEntity

import logging
_LOGGER: logging.Logger = logging.getLogger(__package__)

async def async_setup_entry(hass, entry, async_add_entities):
    try:
        coordinator = hass.data[DOMAIN][entry.entry_id]
        activities = []
        idx = 0
        for device_status in coordinator.data["data"]["device_status"]:
            activity = YaleDoormanViaSmarthubActivity(coordinator, entry, idx)
            activities.append(activity)
            idx = idx + 1
        async_add_entities(activities, True)
    except Exception as exception:
        _LOGGER.error("Failed to set up activity entities: %s", exception, exc_info=True)

class YaleDoormanViaSmarthubActivity(YaleDoormanViaSmarthubEntity, EventEntity):
    """Lock activity from the Yale event log (keypad/app/inside unlocks, locks...)."""

    _attr_event_types = list(dict.fromkeys(ACTIVITY_EVENT_TYPES.values()))
    _attr_translation_key = "activity"
    _attr_icon = "mdi:door"

    def __init__(self, coordinator, config_entry, idx):
        super().__init__(coordinator, config_entry)
        self.idx = idx
        # Only report activity logged after this entity was created
        self._last_seq = coordinator.activity_seq

    @property
    def name(self):
        return f"{self.device_name} Activity"

    @callback
    def _handle_coordinator_update(self) -> None:
        try:
            device = self.coordinator.data["data"]["device_status"][self.idx]
            location = (int(device["area"]), int(device["no"]))
        except (KeyError, IndexError, TypeError, ValueError):
            location = None

        for event in self.coordinator.activity_events:
            if event["seq"] <= self._last_seq:
                continue
            self._last_seq = event["seq"]
            if (event["area"], event["zone"]) != location:
                continue
            self._trigger_event(
                event["event_type"],
                {
                    "user": event["user"],
                    "yale_time": event["yale_time"],
                    "yale_event_code": event["yale_event_code"],
                },
            )
            # One state write per event so each shows up in Activity
            self.async_write_ha_state()

        super()._handle_coordinator_update()
