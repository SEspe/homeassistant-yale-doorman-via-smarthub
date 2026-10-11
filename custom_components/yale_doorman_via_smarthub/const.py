NAME = "Yale Doorman via Smart Hub"
DOMAIN = "yale_doorman_via_smarthub"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "0.0.19"
ISSUE_URL = "https://github.com/SEspe/homeassistant-yale-doorman-via-smarthub/issues"
MANUFACTURER = "Yale"
MODEL = "Doorman"
HUBNAME = "Yale Smart Hub"

BINARY_SENSOR_DEVICE_CLASS = "door"

LOCK = "lock"
BINARY_SENSOR = "binary_sensor"
EVENT = "event"
PLATFORMS = [LOCK, BINARY_SENSOR, EVENT]

# Yale event-log codes for lock activity -> event entity event_type
ACTIVITY_EVENT_TYPES = {
    "1801": "unlocked_inside",
    "1802": "unlocked_outside",
    "1803": "unlocked_app",
    "1807": "auto_relocked",
    "1815": "lock_failed",
    "1816": "locked_after_failure",
    "3801": "locked_inside",
    "3802": "locked_star_button",
    "3803": "locked_app",
}

# Polls in a row to read the event log after a lock/door status change - Yale may
# record the event slightly after the status flips
LOG_FETCH_RETRIES = 3

# Also read the event log every this many polls (10 x 30s = 5 min), to catch activity
# that left the status unchanged, e.g. unlock + open + close + relock between two polls.
# 0 = only read after status changes.
LOG_SAFETY_POLLS = 10

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_PINCODE = "pincode"
CONF_ENABLE_BINARY_SENSOR = "enable_binary_sensor"

BITWISE_CLOSED = 16
BITWISE_LOCKED = 1

STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""
