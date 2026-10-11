"""The Activity event entity, fed from the Yale event log."""
import logging

from homeassistant.const import EVENT_STATE_CHANGED, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback

from custom_components.yale_doorman_via_smarthub.const import LOG_SAFETY_POLLS

from .conftest import (
    ACTIVITY_ENTITY,
    LOG_BASELINE,
    LOG_BURST,
    LOG_URL,
    STATUS_TOKEN,
    UNLOCKED_CLOSED,
    calls_to,
    latest_event,
    log_event,
    mock_yale,
    poll,
    setup_integration,
)


def capture_activity(hass: HomeAssistant) -> list:
    """Collect the attributes of every Activity event the entity fires."""
    fired = []

    @callback
    def _listener(event):
        if event.data["entity_id"] != ACTIVITY_ENTITY:
            return
        new_state = event.data["new_state"]
        if new_state is not None and new_state.attributes.get("event_type"):
            fired.append(dict(new_state.attributes))

    hass.bus.async_listen(EVENT_STATE_CHANGED, _listener)
    return fired


async def test_old_events_not_replayed_at_startup(hass: HomeAssistant, aioclient_mock, config_entry):
    mock_yale(aioclient_mock, log=LOG_BASELINE)
    await setup_integration(hass, config_entry)

    assert hass.states.get(ACTIVITY_ENTITY).state == STATE_UNKNOWN
    reads = calls_to(aioclient_mock, LOG_URL)
    assert len(reads) == 1  # one baseline read
    assert reads[0][1].query["set_utc"] == "1"  # UTC, see _parse_yale_time


async def test_quiet_polls_do_not_read_the_log(hass: HomeAssistant, aioclient_mock, config_entry):
    mock_yale(aioclient_mock)
    await setup_integration(hass, config_entry)

    mock_yale(aioclient_mock)  # nothing happens: same status, same newest event
    for _ in range(LOG_SAFETY_POLLS * 2):
        await poll(hass)

    assert calls_to(aioclient_mock, LOG_URL) == []


async def test_burst_with_unchanged_status_caught_on_next_poll(
    hass: HomeAssistant, aioclient_mock, config_entry
):
    mock_yale(aioclient_mock, log=LOG_BASELINE)
    await setup_integration(hass, config_entry)
    fired = capture_activity(hass)

    # Four events happen between two polls and the lock ends up as it started -
    # only Yale's newest-event id gives it away
    mock_yale(aioclient_mock, log=LOG_BURST, latest=latest_event("1752579372", "1801"))
    await poll(hass)

    assert [event["event_type"] for event in fired] == [
        "locked_star_button",
        "unlocked_outside",
        "locked_inside",
        "unlocked_inside",
    ]
    assert fired[1]["user"] == "Stein"
    assert fired[1]["yale_event_code"] == "1802"
    # 11:21:31 UTC is 13:21:31 in Norwegian summer time
    assert fired[1]["yale_time"] == "2026-10-11T13:21:31+02:00"
    assert len(calls_to(aioclient_mock, LOG_URL)) == 1


async def test_failed_lock_without_status_change(hass: HomeAssistant, aioclient_mock, config_entry):
    """A failed lock leaves the door unlocked - the status never changes."""
    mock_yale(aioclient_mock, lock_status=UNLOCKED_CLOSED)
    await setup_integration(hass, config_entry)
    fired = capture_activity(hass)

    mock_yale(
        aioclient_mock,
        lock_status=UNLOCKED_CLOSED,
        latest=latest_event("1752570001", "1815"),
        log=[log_event("2026/10/11 12:11:02", "1815")] + LOG_BASELINE,
    )
    await poll(hass)

    assert [event["event_type"] for event in fired] == ["lock_failed"]


async def test_log_lagging_behind_is_retried(hass: HomeAssistant, aioclient_mock, config_entry):
    mock_yale(aioclient_mock)
    await setup_integration(hass, config_entry)
    fired = capture_activity(hass)

    new_latest = latest_event("1752578763")
    # Yale reports the new event before it shows up in the log
    mock_yale(aioclient_mock, latest=new_latest, log=LOG_BASELINE)
    await poll(hass)
    assert fired == []

    mock_yale(
        aioclient_mock,
        latest=new_latest,
        log=[log_event("2026/10/11 12:24:03", "1802", "Stein")] + LOG_BASELINE,
    )
    await poll(hass)
    assert [event["event_type"] for event in fired] == ["unlocked_outside"]

    # Found - no more reads while nothing new happens
    for _ in range(4):
        await poll(hass)
    assert len(calls_to(aioclient_mock, LOG_URL)) == 1


async def test_status_change_reads_log_right_away(hass: HomeAssistant, aioclient_mock, config_entry):
    mock_yale(aioclient_mock, log=LOG_BASELINE)
    await setup_integration(hass, config_entry)
    fired = capture_activity(hass)

    new_log = [log_event("2026/10/11 11:30:00", "1803", "Stein")] + LOG_BASELINE
    mock_yale(
        aioclient_mock,
        lock_status=UNLOCKED_CLOSED,
        latest=latest_event("1752580000", "1803"),
        log=new_log,
    )
    await poll(hass)

    assert [(event["event_type"], event["user"]) for event in fired] == [("unlocked_app", "Stein")]

    # Already reported - later reads of the same log must not fire it again
    for _ in range(LOG_SAFETY_POLLS + 1):
        await poll(hass)
    assert len(fired) == 1


async def test_hub_periodic_test_is_ignored_and_read_once(
    hass: HomeAssistant, aioclient_mock, config_entry
):
    mock_yale(aioclient_mock, log=LOG_BASELINE)
    await setup_integration(hass, config_entry)
    fired = capture_activity(hass)

    mock_yale(
        aioclient_mock,
        latest=latest_event("1752590000", "1602"),
        log=[log_event("2026/10/11 11:30:00", "1602", area="0", zone="0")] + LOG_BASELINE,
    )
    for _ in range(4):
        await poll(hass)

    assert fired == []
    assert len(calls_to(aioclient_mock, LOG_URL)) == 1


async def test_fallback_safety_read_without_latest_event(
    hass: HomeAssistant, aioclient_mock, config_entry
):
    """Older responses without report_event_latest still get the timed safety read."""
    mock_yale(aioclient_mock, latest=None, log=LOG_BASELINE)
    await setup_integration(hass, config_entry)
    fired = capture_activity(hass)

    mock_yale(aioclient_mock, latest=None, log=LOG_BURST)
    for _ in range(LOG_SAFETY_POLLS + 2):
        await poll(hass)
        if fired:
            break

    assert len(fired) == 4
    assert len(calls_to(aioclient_mock, LOG_URL)) == 1


async def test_status_token_not_logged(hass: HomeAssistant, aioclient_mock, config_entry, caplog):
    caplog.set_level(logging.DEBUG, logger="custom_components.yale_doorman_via_smarthub")
    mock_yale(aioclient_mock)
    await setup_integration(hass, config_entry)

    assert "Panel status response" in caplog.text
    assert STATUS_TOKEN not in caplog.text
