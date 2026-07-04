import logging
import asyncio
import socket
from typing import Optional
import aiohttp
import async_timeout
from datetime import datetime, timedelta
import pickle
import os

TIMEOUT = 10


_LOGGER: logging.Logger = logging.getLogger(__package__)

HEADERS = {"Content-type": "application/json; charset=UTF-8"}


class YaleDoormanViaSmarthubApiClient:
    def __init__(
        self, username: str, password: str, session: aiohttp.ClientSession
    ) -> None:
        self._username = username
        self._password = password
        self._session = session
        self._access_token = None
        self._refresh_token = None
        self._token_expires = None

    async def async_login(self):
        if self._access_token is not None and self._token_expires is not None:
            if self._token_expires > datetime.now():
                _LOGGER.debug(
                    "Reusing cached access token (expires %s)", self._token_expires
                )
                return True
            else:
                # Refresh token
                # Left as an exercise to the reader :)
                _LOGGER.debug("Cached access token expired at %s, re-authenticating", self._token_expires)

        hub_login_path = os.path.join(os.path.dirname(__file__), "hub.login")
        try:
            with open(hub_login_path, 'rb') as f:
                hub_login = pickle.load(f)
        except FileNotFoundError:
            _LOGGER.error(
                "hub.login file not found at %s - cannot authenticate with Yale API",
                hub_login_path,
            )
            return False
        except Exception as exception:
            _LOGGER.error("Failed to read hub.login file at %s: %s", hub_login_path, exception)
            return False

        auth = aiohttp.BasicAuth(hub_login["u"], hub_login["p"])
        url = "https://mob.yalehomesystem.co.uk/yapi/o/token/"
        data = {"grant_type": "password", "username": self._username, "password": self._password}
        headers = {"Accept": "application/json"}
        _LOGGER.debug("Requesting new access token for user %s from %s", self._username, url)
        result = await self.api_wrapper("post",url,data,headers,auth)
        try:
            self._access_token = result["access_token"]
            self._refresh_token = result["refresh_token"]
            self._token_expires = datetime.now() + timedelta(seconds=result["expires_in"])
            _LOGGER.debug("Login succeeded, new token expires at %s", self._token_expires)
            return True
        except Exception as exception:
            _LOGGER.error("Login failed, could not parse token response %s: %s", result, exception)
            return False

    async def async_status(self) -> dict:
        try:
            logged_in = await self.async_login()
            if not logged_in:
                _LOGGER.warning("Skipping status refresh because login failed")
                return None
            url = "https://mob.yalehomesystem.co.uk/yapi/api/panel/cycle/"
            headers = {"Authorization": f"Bearer {self._access_token}"}
            data = {}
            _LOGGER.debug("Requesting panel status from %s", url)
            result = await self.api_wrapper("get",url,data,headers)
            if result is None:
                _LOGGER.warning("Panel status request to %s returned no data", url)
            else:
                _LOGGER.debug("Panel status response: %s", result)
            return result
        except Exception as exception:
            _LOGGER.error("Unexpected error fetching panel status: %s", exception, exc_info=True)
    
    async def async_lock(self, device_id: str, area: int = 1, zone: int = 1) -> bool:
        try:
            if not await self.async_login():
                _LOGGER.warning("Skipping lock command because login failed")
                return False

            data = aiohttp.FormData()
            data.add_field("area",area)
            data.add_field("zone",zone)
            data.add_field("device_sid",device_id)
            data.add_field("device_type","device_type.door_lock")
            data.add_field("request_value",1)

            headers = {
                "Authorization": f"Bearer {self._access_token}"
            }

            url = "https://mob.yalehomesystem.co.uk/yapi/api/panel/device_control/"

            _LOGGER.debug("Sending lock command for device %s (area=%s, zone=%s)", device_id, area, zone)
            result = await self.api_wrapper("post", url, data, headers)
            _LOGGER.debug("Lock command response: %s", result)
            if result and result["code"] == "000":
                return True
        except Exception as exception:
            _LOGGER.error("Unexpected error sending lock command: %s", exception, exc_info=True)
        return False

    async def async_unlock(self, device_id: str, area: int = 1, zone: int = 1, pincode: str = "") -> bool:
        try:
            if not await self.async_login():
                _LOGGER.warning("Skipping unlock command because login failed")
                return False

            data = aiohttp.FormData()
            data.add_field("area",area)
            data.add_field("zone",zone)
            data.add_field("pincode",pincode)

            headers = {
                "Authorization": f"Bearer {self._access_token}"
            }

            url = "https://mob.yalehomesystem.co.uk/yapi/api/minigw/unlock/"

            _LOGGER.debug("Sending unlock command for device %s (area=%s, zone=%s)", device_id, area, zone)
            result = await self.api_wrapper("post", url, data, headers)
            _LOGGER.debug("Unlock command response: %s", result)
            if result and result["code"] == "000":
                return True
        except Exception as exception:
            _LOGGER.error("Unexpected error sending unlock command: %s", exception, exc_info=True)
        return False
    
    async def api_wrapper(self, method: str, url: str, data: dict = {}, headers: dict = {}, auth = None) -> dict:
        safe_headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}
        _LOGGER.debug("%s request to %s (headers=%s)", method.upper(), url, safe_headers)
        try:
            async with async_timeout.timeout(TIMEOUT):
                if method == "get":
                    response = await self._session.get(url, headers=headers, auth=auth)
                elif method == "put":
                    response = await self._session.put(url, headers=headers, json=data, auth=auth)
                elif method == "patch":
                    response = await self._session.patch(url, headers=headers, json=data, auth=auth)
                elif method == "post":
                    response = await self._session.post(url, headers=headers, data=data, auth=auth)
                else:
                    _LOGGER.error("Unknown HTTP method %s requested for %s", method, url)
                    return None

                _LOGGER.debug("Response from %s: HTTP %s", url, response.status)

                if response.status >= 400:
                    body_text = await response.text()
                    _LOGGER.error(
                        "Yale API returned HTTP %s for %s %s - body: %s",
                        response.status,
                        method.upper(),
                        url,
                        body_text,
                    )
                    return None

                if method in ("get", "post"):
                    result = await response.json()
                    return result
                return None

        except asyncio.TimeoutError as exception:
            _LOGGER.error(
                "Timeout after %ss fetching information from %s - %s",
                TIMEOUT,
                url,
                exception,
            )

        except (KeyError, TypeError) as exception:
            _LOGGER.error(
                "Error parsing information from %s - %s",
                url,
                exception,
            )
        except (aiohttp.ClientError, socket.gaierror) as exception:
            _LOGGER.error(
                "Error fetching information from %s (is the Yale/smarthub backend reachable?) - %s",
                url,
                exception,
            )
        except Exception as exception:
            _LOGGER.error("Something really wrong happened calling %s! - %s", url, exception, exc_info=True)

    async def async_get_yale_event_log(self, page_number: str = "1") -> dict:
        """
        Download the last month's event log from Yale API.
        """
        try:
            url = f"https://mob.yalehomesystem.co.uk/yapi/api/event/report/?page_num={page_number}&set_utc=0"
            data = {}
            headers = {
                    "Authorization": f"Bearer {self._access_token}"
            }
            _LOGGER.info("Downloaded page %s from Yale event log. url: %s", page_number, url)
            return await self.api_wrapper("get", url, data, headers)

        except Exception as exception:
            _LOGGER.error("Failed to fetch Yale event log (page %s): %s", page_number, exception)
