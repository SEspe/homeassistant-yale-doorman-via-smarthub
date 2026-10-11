"""The Activity event entity, fed from the Yale event log."""
from homeassistant.const import EVENT_STATE_CHANGED, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback

from custom_components.yale_doorman_via_smarthub.const import LOG_SAFETY_POLLS

from .conftest import (
    ACTIVITY_ENTITY,
    LOG_BASELINE,
    LOG_BURST,
    LOG_URL,
    UNLOCKED_CLOSED,
    calls_to,
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


async def test_burst_with_unchanged_status_is_caught_by_safety_read(
    hass: HomeAssistant, aioclient_mock, config_entry
):
    mock_yale(aioclient_mock, log=LOG_BASELINE)
    await setup_integration(hass, config_entry)
    fired = capture_activity(hass)

    # Four events happen between two polls and the lock ends up as it started
    mock_yale(aioclient_mock, log=LOG_BURST)
    for _ in range(LOG_SAFETY_POLLS + 2):
        await poll(hass)
        if fired:
            break

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
    # Quiet polls before the safety read cost no extra log reads
    assert len(calls_to(aioclient_mock, LOG_URL)) == 1


async def test_status_change_reads_log_right_away(hass: HomeAssistant, aioclient_mock, config_entry):
    mock_yale(aioclient_mock, log=LOG_BASELINE)
    await setup_integration(hass, config_entry)
    fired = capture_activity(hass)

    mock_yale(
        aioclient_mock,
        lock_status=UNLOCKED_CLOSED,
        log=[log_event("2026/10/11 11:30:00", "1803", "Stein")] + LOG_BASELINE,
    )
    await poll(hass)

    assert [(event["event_type"], event["user"]) for event in fired] == [("unlocked_app", "Stein")]

    # Already reported - later reads of the same log must not fire it again
    for _ in range(LOG_SAFETY_POLLS + 1):
        await poll(hass)
    assert len(fired) == 1


async def test_non_lock_events_are_ignored(hass: HomeAssistant, aioclient_mock, config_entry):
    mock_yale(aioclient_mock, log=LOG_BASELINE)
    await setup_integration(hass, config_entry)
    fired = capture_activity(hass)

    mock_yale(
        aioclient_mock,
        lock_status=UNLOCKED_CLOSED,
        log=[log_event("2026/10/11 11:30:00", "1602", area="0", zone="0")] + LOG_BASELINE,
    )
    await poll(hass)

    assert fired == []
