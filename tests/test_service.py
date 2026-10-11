"""The download_yale_event_log service action."""
from homeassistant.core import HomeAssistant

from custom_components.yale_doorman_via_smarthub.const import DOMAIN

from .conftest import LOG_BASELINE, LOG_URL, calls_to, log_event, mock_yale, setup_integration


async def _download(hass: HomeAssistant, **data) -> dict:
    return await hass.services.async_call(
        DOMAIN, "download_yale_event_log", data, blocking=True, return_response=True
    )


async def test_download_in_norwegian_and_utc(hass: HomeAssistant, aioclient_mock, config_entry):
    mock_yale(aioclient_mock, log=LOG_BASELINE)
    await setup_integration(hass, config_entry)
    hass.config.language = "nb"
    aioclient_mock.mock_calls.clear()

    response = await _download(hass, pages="1", utc=True)

    assert response["total_rows_returned"] == len(LOG_BASELINE)
    assert response["pages_fetched"] == 1
    assert response["event_log_table"][0] == {
        "Time": "2026/10/11 11:19:49",
        "Event": "Låst opp utenfra med brikke eller kode",
        "Device": "Ytterdør",
        "Name": "Stein",
    }
    assert calls_to(aioclient_mock, LOG_URL)[0][1].query["set_utc"] == "1"


async def test_download_falls_back_to_english(hass: HomeAssistant, aioclient_mock, config_entry):
    mock_yale(aioclient_mock, log=LOG_BASELINE)
    await setup_integration(hass, config_entry)
    hass.config.language = "de"

    response = await _download(hass)

    assert response["event_log_table"][0]["Event"] == "Unlocked from outside, token or keypad"
    assert calls_to(aioclient_mock, LOG_URL)[-1][1].query["set_utc"] == "0"  # default: hub time


async def test_download_all_pages(hass: HomeAssistant, aioclient_mock, config_entry):
    mock_yale(aioclient_mock, log=LOG_BASELINE)
    await setup_integration(hass, config_entry)

    # Two pages of events, then an empty page
    mock_yale(aioclient_mock, log=None)
    aioclient_mock.get(f"{LOG_URL}?page_num=1", json={"data": LOG_BASELINE})
    aioclient_mock.get(f"{LOG_URL}?page_num=2", json={"data": [log_event("2026/10/01 08:00:00", "3801")]})
    aioclient_mock.get(f"{LOG_URL}?page_num=3", json={"data": []})

    response = await _download(hass, pages="*")

    assert response["pages_fetched"] == 2
    assert response["total_rows_returned"] == len(LOG_BASELINE) + 1
    assert len(calls_to(aioclient_mock, LOG_URL)) == 3
