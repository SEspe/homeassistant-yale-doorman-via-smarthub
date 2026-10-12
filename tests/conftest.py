"""Shared fixtures: a faked Yale cloud API and a config entry for one Doorman lock."""
from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.yale_doorman_via_smarthub.const import DOMAIN

pytest_plugins = "pytest_homeassistant_custom_component"

BASE = "https://mob.yalehomesystem.co.uk/yapi"
TOKEN_URL = f"{BASE}/o/token/"
STATUS_URL = f"{BASE}/api/panel/cycle/"
LOG_URL = f"{BASE}/api/event/report/"
LOCK_URL = f"{BASE}/api/panel/device_control/"
UNLOCK_URL = f"{BASE}/api/minigw/unlock/"

INVALID_GRANT = '{"error": "invalid_grant", "error_description": "Invalid credentials given."}'

# minigw_lock_status is hex: bit 16 = door closed, bit 1 = locked. Real values seen:
# "15" locked, "14"/"10" unlocked (door closed)
LOCKED_CLOSED = "15"
UNLOCKED_CLOSED = "14"

# Yale session token carried in every status response - must never reach the log
STATUS_TOKEN = "SECRET-SESSION-TOKEN"

LOCK_ENTITY = "lock.ytterdor"
DOOR_ENTITY = "binary_sensor.ytterdor"
ACTIVITY_ENTITY = "event.ytterdor_activity"

ENTRY_DATA = {
    "username": "stein@example.com",
    "password": "old-password",
    "pincode": "123456",
    "enable_binary_sensor": True,
}


def log_event(time, code, name=None, area="1", zone="1"):
    return {"time": time, "event_type": code, "area": area, "zone": zone, "name": name}


# Based on a real Yale event log, times in UTC (set_utc=1), newest first
LOG_BASELINE = [
    log_event("2026/10/11 11:19:49", "1802", "Stein"),
    log_event("2026/10/11 11:19:45", "3802"),
    log_event("2026/10/11 11:19:37", "1801"),
    log_event("2026/10/11 11:19:31", "3801"),
    log_event("2026/10/11 09:35:34", "1803", "Stein"),
    log_event("2026/10/10 23:28:38", "1602", area="0", zone="0"),
]
# Four lock events within 15 seconds; the lock ends up as it started
LOG_BURST = [
    log_event("2026/10/11 11:21:39", "1801"),
    log_event("2026/10/11 11:21:37", "3801"),
    log_event("2026/10/11 11:21:31", "1802", "Stein"),
    log_event("2026/10/11 11:21:24", "3802"),
] + LOG_BASELINE


def latest_event(report_id, code="1802", time="1791720851"):
    """Yale's newest event, as carried in every status response (report_event_latest)."""
    return {
        "utc_event_time": None,
        "time": time,
        "report_id": report_id,
        "id": f"18{code[1:]}0201102",
        "event_time": None,
        "cid_code": code,
    }


LATEST_BASELINE = latest_event("1752573860")


def status_response(lock_status=LOCKED_CLOSED, latest=LATEST_BASELINE):
    """Shaped like a real panel/cycle response (trimmed)."""
    return {
        "result": True,
        "code": "000",
        "message": "OK!",
        "token": STATUS_TOKEN,
        "data": {
            "model": [{"area": "1", "mode": "disarm"}],
            "device_status": [
                {
                    "area": "1",
                    "no": "1",
                    "address": "RF:0123abcd",
                    "type": "device_type.door_lock",
                    "name": "Ytterdør",
                    "status1": "device_status.lock" if lock_status == LOCKED_CLOSED else "device_status.unlock",
                    "device_id": "RF:0123abcd",
                    "minigw_lock_status": lock_status,
                }
            ],
            "capture_latest": None,
            "report_event_latest": latest,
            "alarm_event_latest": None,
        },
    }


def mock_yale(
    aioclient_mock,
    *,
    token_status=200,
    lock_status=LOCKED_CLOSED,
    latest=LATEST_BASELINE,
    log=LOG_BASELINE,
    expires_in=3600,
    command_code="000",
):
    """(Re)register the faked Yale API. Also clears the recorded calls.

    command_code is Yale's answer to lock/unlock commands - "000" means OK.
    log=None leaves the event log unregistered, for tests that register pages themselves.
    """
    aioclient_mock.clear_requests()
    if token_status == 200:
        aioclient_mock.post(
            TOKEN_URL,
            json={"access_token": "token", "refresh_token": "refresh", "expires_in": expires_in},
        )
    elif token_status == 401:
        aioclient_mock.post(TOKEN_URL, status=401, text=INVALID_GRANT)
    else:
        aioclient_mock.post(TOKEN_URL, status=token_status, text="Service Unavailable")
    aioclient_mock.get(STATUS_URL, json=status_response(lock_status, latest))
    if log is not None:
        aioclient_mock.get(LOG_URL, json={"data": log})
    aioclient_mock.post(LOCK_URL, json={"code": command_code})
    aioclient_mock.post(UNLOCK_URL, json={"code": command_code})


def calls_to(aioclient_mock, url):
    path = url.removeprefix("https://mob.yalehomesystem.co.uk")
    return [call for call in aioclient_mock.mock_calls if call[1].path == path]


async def poll(hass: HomeAssistant):
    """Let the 30-second coordinator poll run once."""
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> bool:
    result = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return result


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def fail_on_home_assistant_deprecation_reports(caplog):
    """Fail when HA reports that this integration uses something that will stop working.

    HA only logs these ("Detected that custom integration ... will stop working in
    Home Assistant 2026.x", deprecated constants, blocking calls) - it doesn't raise,
    so without this check they would pass unnoticed.
    """
    yield
    reports = [
        record.getMessage()
        for record in caplog.get_records("call")
        if DOMAIN in record.getMessage()
        and any(
            word in record.getMessage().lower()
            for word in ("deprecat", "stop working", "will be removed", "detected")
        )
    ]
    assert not reports, reports


@pytest.fixture(autouse=True)
async def norwegian_time_zone(hass: HomeAssistant):
    await hass.config.async_set_time_zone("Europe/Oslo")


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title=ENTRY_DATA["username"], data=dict(ENTRY_DATA))
    entry.add_to_hass(hass)
    return entry
