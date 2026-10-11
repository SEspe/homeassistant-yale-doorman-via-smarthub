from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
import voluptuous as vol
import logging

from .api import YaleAuthError, YaleDoormanViaSmarthubApiClient

from .const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_PINCODE,
    CONF_ENABLE_BINARY_SENSOR,
    BINARY_SENSOR,
    DOMAIN,
    PLATFORMS,
)

_LOGGER: logging.Logger = logging.getLogger(__package__)

async def _async_check_login(hass, username, password):
    """Try the credentials against Yale. Returns an error key, or None if they work."""
    try:
        session = async_create_clientsession(hass)
        client = YaleDoormanViaSmarthubApiClient(hass, username, password, session)
        if await client.async_login():
            return None
        return "cannot_connect"
    except YaleAuthError:
        return "auth"
    except Exception as exception:
        _LOGGER.error("Unexpected error checking Yale login: %s", exception, exc_info=True)
        return "cannot_connect"

class YaleDoormanViaSmarthubFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL
    
    def __init__(self):
        self._errors = {}
    
    async def async_step_user(self, user_input=None):
        self._errors = {}
        
        if user_input is not None:
            error = await _async_check_login(self.hass, user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
            if error is None:
                return self.async_create_entry(
                    title = user_input[CONF_USERNAME],
                    data = user_input, 
                )
            self._errors["base"] = error
        
        return await self._show_config_form(user_input)

    async def async_step_reauth(self, entry_data):
        """Started by HA when the coordinator raises ConfigEntryAuthFailed."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        self._errors = {}
        entry = self._get_reauth_entry()
        username = entry.data.get(CONF_USERNAME)

        if user_input is not None:
            error = await _async_check_login(self.hass, username, user_input[CONF_PASSWORD])
            if error is None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
            self._errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"username": username},
            errors=self._errors,
        )
    
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return YaleDoormanViaSmarthubOptionsFlowHandler()

    async def _show_config_form(self, user_input):
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str, 
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(CONF_PINCODE): str,
                    vol.Required(CONF_ENABLE_BINARY_SENSOR, default = True): bool
                }
            ),
            errors=self._errors,
        )

class YaleDoormanViaSmarthubOptionsFlowHandler(config_entries.OptionsFlow):
    # Don't store config_entry ourselves - modern Home Assistant provides it as a
    # read-only property (self.config_entry); assigning to it raises and the options
    # flow fails to load with a 500.

    async def async_step_init(self, user_input=None):
        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            data = self.config_entry.data
            if (user_input[CONF_USERNAME], user_input[CONF_PASSWORD]) != (data.get(CONF_USERNAME), data.get(CONF_PASSWORD)):
                error = await _async_check_login(self.hass, user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
                if error is not None:
                    errors["base"] = error
            if not errors:
                return await self._update_options(user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default = self.config_entry.data.get(CONF_USERNAME)): str,
                    vol.Required(CONF_PASSWORD, default = self.config_entry.data.get(CONF_PASSWORD)): str,
                    vol.Optional(CONF_PINCODE, default = self.config_entry.data.get(CONF_PINCODE)): str,
                    vol.Required(CONF_ENABLE_BINARY_SENSOR, default = self.config_entry.data.get(CONF_ENABLE_BINARY_SENSOR, True)): bool
                }
            ),
            errors=errors,
        )

    async def _update_options(self, user_input):
        # Everything (username/password/pincode/enable_binary_sensor) lives in
        # config_entry.data, not .options - merge the submitted fields over the
        # existing data. async_update_entry persists it and the update listener
        # registered in __init__.py reloads the entry.
        data = {**self.config_entry.data, **user_input}
        self.hass.config_entries.async_update_entry(self.config_entry, data=data)

        return self.async_create_entry(title="", data={})
