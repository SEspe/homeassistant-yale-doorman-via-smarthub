"""Door binary sensor: open/closed from the lock status, and the on/off option."""
import pytest
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from .conftest import (
    DOOR_ENTITY,
    ENTRY_DATA,
    LOCK_ENTITY,
    LOCKED_CLOSED,
    mock_yale,
    poll,
    setup_integration,
)

DOOR_OPEN = "05"  # bit 16 clear = door open


@pytest.mark.parametrize(
    ("lock_status", "state", "lock", "icon"),
    [
        ("15", STATE_OFF, "locked", "mdi:door-closed-lock"),
        ("14", STATE_OFF, "unlocked", "mdi:door-closed"),
        ("10", STATE_OFF, "unlocked", "mdi:door-closed"),
        (DOOR_OPEN, STATE_ON, "unlocked", "mdi:door-open"),
    ],
)
async def test_door_status(
    hass: HomeAssistant, aioclient_mock, config_entry, lock_status, state, lock, icon
):
    mock_yale(aioclient_mock, lock_status=lock_status)
    await setup_integration(hass, config_entry)

    door = hass.states.get(DOOR_ENTITY)
    assert door.state == state
    assert door.attributes["device_class"] == "door"
    assert door.attributes["lock"] == lock
    assert door.attributes["icon"] == icon


async def test_door_follows_yale_status(hass: HomeAssistant, aioclient_mock, config_entry):
    mock_yale(aioclient_mock, lock_status=LOCKED_CLOSED)
    await setup_integration(hass, config_entry)

    mock_yale(aioclient_mock, lock_status=DOOR_OPEN)
    await poll(hass)
    assert hass.states.get(DOOR_ENTITY).state == STATE_ON

    mock_yale(aioclient_mock, lock_status=LOCKED_CLOSED)
    await poll(hass)
    assert hass.states.get(DOOR_ENTITY).state == STATE_OFF


async def test_door_sensor_turned_off(hass: HomeAssistant, aioclient_mock, config_entry):
    hass.config_entries.async_update_entry(
        config_entry, data={**ENTRY_DATA, "enable_binary_sensor": False}
    )
    mock_yale(aioclient_mock)
    await setup_integration(hass, config_entry)

    assert hass.states.get(DOOR_ENTITY) is None
    assert hass.states.get(LOCK_ENTITY).state == "locked"


async def test_door_sensor_on_when_option_missing(hass: HomeAssistant, aioclient_mock, config_entry):
    """Entries made before the option existed get the door sensor."""
    data = dict(ENTRY_DATA)
    del data["enable_binary_sensor"]
    hass.config_entries.async_update_entry(config_entry, data=data)
    mock_yale(aioclient_mock)
    await setup_integration(hass, config_entry)

    assert hass.states.get(DOOR_ENTITY).state == STATE_OFF
