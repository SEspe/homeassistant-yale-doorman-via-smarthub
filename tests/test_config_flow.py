"""Setup, reauth and Configure dialogs."""
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.yale_doorman_via_smarthub.const import DOMAIN

from .conftest import ENTRY_DATA, mock_yale, poll, setup_integration

NEW_LOGIN = {
    "username": "stein@example.com",
    "password": "new-password",
    "pincode": "123456",
    "enable_binary_sensor": True,
}


async def _start_user_flow(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    return result


async def test_user_flow_creates_entry(hass: HomeAssistant, aioclient_mock):
    mock_yale(aioclient_mock)
    result = await _start_user_flow(hass)

    with patch(
        "custom_components.yale_doorman_via_smarthub.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], NEW_LOGIN)
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == NEW_LOGIN


async def test_user_flow_wrong_password(hass: HomeAssistant, aioclient_mock):
    mock_yale(aioclient_mock, token_status=401)
    result = await _start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], NEW_LOGIN)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "auth"}


async def test_user_flow_yale_unreachable(hass: HomeAssistant, aioclient_mock):
    mock_yale(aioclient_mock, token_status=503)
    result = await _start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], NEW_LOGIN)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


def _reauth_flows(hass: HomeAssistant):
    return [
        flow
        for flow in hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        if flow["context"]["source"] == config_entries.SOURCE_REAUTH
    ]


async def test_changed_password_at_startup_asks_for_new_one(
    hass: HomeAssistant, aioclient_mock, config_entry
):
    mock_yale(aioclient_mock, token_status=401)
    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = _reauth_flows(hass)
    assert len(flows) == 1

    # A wrong new password is rejected
    result = await hass.config_entries.flow.async_configure(
        flows[0]["flow_id"], {"password": "still-wrong"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "auth"}

    # The right one is saved and the integration restarts
    mock_yale(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(
        flows[0]["flow_id"], {"password": "new-password"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data["password"] == "new-password"
    assert config_entry.state is ConfigEntryState.LOADED


async def test_changed_password_while_running_asks_for_new_one(
    hass: HomeAssistant, aioclient_mock, config_entry
):
    # Token expires at once, so every poll logs in again
    mock_yale(aioclient_mock, expires_in=0)
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    mock_yale(aioclient_mock, token_status=401)
    await poll(hass)

    assert len(_reauth_flows(hass)) == 1


async def test_options_flow_checks_new_password(hass: HomeAssistant, aioclient_mock, config_entry):
    mock_yale(aioclient_mock)
    await setup_integration(hass, config_entry)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    mock_yale(aioclient_mock, token_status=401)
    result = await hass.config_entries.options.async_configure(result["flow_id"], NEW_LOGIN)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "auth"}
    assert config_entry.data["password"] == ENTRY_DATA["password"]

    mock_yale(aioclient_mock)
    result = await hass.config_entries.options.async_configure(result["flow_id"], NEW_LOGIN)
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.data["password"] == "new-password"
