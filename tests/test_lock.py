"""Lock entity: reading the lock status, lock/unlock commands and the PIN-code."""
import pytest
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from .conftest import (
    ENTRY_DATA,
    LOCK_ENTITY,
    LOCK_URL,
    LOCKED_CLOSED,
    STATUS_URL,
    TOKEN_URL,
    UNLOCK_URL,
    UNLOCKED_CLOSED,
    calls_to,
    mock_yale,
    poll,
    setup_integration,
)

SIX_DIGITS_OR_NOTHING = r"^(\d{6})?$"


def form_fields(call):
    """The form fields of a recorded lock/unlock request, as {name: str(value)}."""
    return {field[0]["name"]: str(field[2]) for field in call[2]._fields}


def without_pincode(hass: HomeAssistant, config_entry):
    hass.config_entries.async_update_entry(config_entry, data={**ENTRY_DATA, "pincode": ""})


@pytest.mark.parametrize(
    ("lock_status", "state", "door", "icon"),
    [
        ("15", "locked", "closed", "mdi:lock"),
        ("14", "unlocked", "closed", "mdi:lock-open-variant"),
        ("10", "unlocked", "closed", "mdi:lock-open-variant"),
        # Bit 16 clear = door open. Never reported locked, even with the lock bit set
        ("05", "unlocked", "open", "mdi:door-open"),
    ],
)
async def test_lock_status(
    hass: HomeAssistant, aioclient_mock, config_entry, lock_status, state, door, icon
):
    mock_yale(aioclient_mock, lock_status=lock_status)
    await setup_integration(hass, config_entry)

    lock = hass.states.get(LOCK_ENTITY)
    assert lock.state == state
    assert lock.attributes["door"] == door
    assert lock.attributes["icon"] == icon


async def test_lock_follows_yale_status(hass: HomeAssistant, aioclient_mock, config_entry):
    mock_yale(aioclient_mock, lock_status=LOCKED_CLOSED)
    await setup_integration(hass, config_entry)
    assert hass.states.get(LOCK_ENTITY).state == "locked"

    mock_yale(aioclient_mock, lock_status=UNLOCKED_CLOSED)
    await poll(hass)
    assert hass.states.get(LOCK_ENTITY).state == "unlocked"


async def test_missing_lock_status_keeps_last_known(hass: HomeAssistant, aioclient_mock, config_entry):
    mock_yale(aioclient_mock, lock_status=LOCKED_CLOSED)
    await setup_integration(hass, config_entry)

    mock_yale(aioclient_mock, lock_status=None)
    await poll(hass)
    assert hass.states.get(LOCK_ENTITY).state == "locked"


async def test_unavailable_while_yale_is_down(hass: HomeAssistant, aioclient_mock, config_entry):
    mock_yale(aioclient_mock)
    await setup_integration(hass, config_entry)

    aioclient_mock.clear_requests()
    aioclient_mock.post(
        TOKEN_URL, json={"access_token": "token", "refresh_token": "refresh", "expires_in": 3600}
    )
    aioclient_mock.get(STATUS_URL, status=500, text="Internal Server Error")
    await poll(hass)
    assert hass.states.get(LOCK_ENTITY).state == STATE_UNAVAILABLE

    mock_yale(aioclient_mock)
    await poll(hass)
    assert hass.states.get(LOCK_ENTITY).state == "locked"


async def test_lock_command_sends_the_right_lock(hass: HomeAssistant, aioclient_mock, config_entry):
    mock_yale(aioclient_mock, lock_status=UNLOCKED_CLOSED)
    await setup_integration(hass, config_entry)

    await hass.services.async_call("lock", "lock", {"entity_id": LOCK_ENTITY}, blocking=True)
    assert form_fields(calls_to(aioclient_mock, LOCK_URL)[0]) == {
        "area": "1",
        "zone": "1",
        "device_sid": "RF:0123abcd",
        "device_type": "device_type.door_lock",
        "request_value": "1",
    }


async def test_typed_code_is_used_instead_of_stored_pin(hass: HomeAssistant, aioclient_mock, config_entry):
    mock_yale(aioclient_mock)
    await setup_integration(hass, config_entry)
    # A stored PIN-code means HA doesn't ask for one
    assert hass.states.get(LOCK_ENTITY).attributes.get("code_format") is None

    await hass.services.async_call(
        "lock", "unlock", {"entity_id": LOCK_ENTITY, "code": "654321"}, blocking=True
    )
    assert form_fields(calls_to(aioclient_mock, UNLOCK_URL)[0])["pincode"] == "654321"


async def test_without_stored_pin_unlock_needs_six_digits(hass: HomeAssistant, aioclient_mock, config_entry):
    without_pincode(hass, config_entry)
    mock_yale(aioclient_mock)
    await setup_integration(hass, config_entry)
    assert hass.states.get(LOCK_ENTITY).attributes["code_format"] == SIX_DIGITS_OR_NOTHING

    with pytest.raises(ServiceValidationError) as no_code:
        await hass.services.async_call("lock", "unlock", {"entity_id": LOCK_ENTITY}, blocking=True)
    assert no_code.value.translation_key == "code_required"
    for code in ("12", "abcdef"):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                "lock", "unlock", {"entity_id": LOCK_ENTITY, "code": code}, blocking=True
            )
    assert not calls_to(aioclient_mock, UNLOCK_URL)

    await hass.services.async_call(
        "lock", "unlock", {"entity_id": LOCK_ENTITY, "code": "654321"}, blocking=True
    )
    assert form_fields(calls_to(aioclient_mock, UNLOCK_URL)[0])["pincode"] == "654321"
    assert hass.states.get(LOCK_ENTITY).state == "unlocked"


async def test_without_stored_pin_lock_needs_no_code(hass: HomeAssistant, aioclient_mock, config_entry):
    """Yale needs no code to lock, so neither does HA - even when unlocking asks for one."""
    without_pincode(hass, config_entry)
    mock_yale(aioclient_mock, lock_status=UNLOCKED_CLOSED)
    await setup_integration(hass, config_entry)

    await hass.services.async_call("lock", "lock", {"entity_id": LOCK_ENTITY}, blocking=True)
    assert "pincode" not in form_fields(calls_to(aioclient_mock, LOCK_URL)[0])
    assert hass.states.get(LOCK_ENTITY).state == "locked"

    # The UI still shows a code field when locking; a typed code is accepted and ignored
    await hass.services.async_call(
        "lock", "lock", {"entity_id": LOCK_ENTITY, "code": "654321"}, blocking=True
    )
    assert len(calls_to(aioclient_mock, LOCK_URL)) == 2


@pytest.mark.parametrize(
    ("service", "start", "url"),
    [
        ("unlock", LOCKED_CLOSED, UNLOCK_URL),
        ("lock", UNLOCKED_CLOSED, LOCK_URL),
    ],
)
async def test_refused_command_leaves_state_alone(
    hass: HomeAssistant, aioclient_mock, config_entry, service, start, url
):
    mock_yale(aioclient_mock, lock_status=start, command_code="999")
    await setup_integration(hass, config_entry)
    state_before = hass.states.get(LOCK_ENTITY).state

    await hass.services.async_call("lock", service, {"entity_id": LOCK_ENTITY}, blocking=True)
    assert len(calls_to(aioclient_mock, url)) == 1
    assert hass.states.get(LOCK_ENTITY).state == state_before
