"""Setup, entities and lock/unlock commands."""
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .conftest import (
    ACTIVITY_ENTITY,
    DOOR_ENTITY,
    LOCK_ENTITY,
    LOCK_URL,
    UNLOCK_URL,
    calls_to,
    mock_yale,
    setup_integration,
)


async def test_setup_creates_entities(hass: HomeAssistant, aioclient_mock, config_entry):
    mock_yale(aioclient_mock)
    assert await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(LOCK_ENTITY).state == "locked"
    assert hass.states.get(DOOR_ENTITY).state == STATE_OFF  # closed
    assert hass.states.get(ACTIVITY_ENTITY).state == STATE_UNKNOWN  # nothing new yet


async def test_setup_retries_when_yale_is_down(hass: HomeAssistant, aioclient_mock, config_entry):
    mock_yale(aioclient_mock, token_status=503)
    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    # A server error is not a password problem - no reauth prompt
    assert not hass.config_entries.flow.async_progress_by_handler(config_entry.domain)


async def test_unlock_and_lock(hass: HomeAssistant, aioclient_mock, config_entry):
    mock_yale(aioclient_mock)
    await setup_integration(hass, config_entry)

    await hass.services.async_call("lock", "unlock", {"entity_id": LOCK_ENTITY}, blocking=True)
    unlock_calls = calls_to(aioclient_mock, UNLOCK_URL)
    assert len(unlock_calls) == 1
    # No code typed, so the PIN from the config entry is sent
    assert "123456" in [field[2] for field in unlock_calls[0][2]._fields]
    assert hass.states.get(LOCK_ENTITY).state == "unlocked"

    await hass.services.async_call("lock", "lock", {"entity_id": LOCK_ENTITY}, blocking=True)
    assert len(calls_to(aioclient_mock, LOCK_URL)) == 1
    assert hass.states.get(LOCK_ENTITY).state == "locked"
