# homeassistant-yale-doorman-via-smarthub
A Home Assistant integration to control a Yale Doorman lock via the Yale Smart Hub.
So far only tested on a single Yale Doorman V2N.

> Based on [jockesyk/homeassistant-yale-doorman-via-smarthub](https://github.com/jockesyk/homeassistant-yale-doorman-via-smarthub)
> by Joakim Syk, licensed under GPL v3. See `CHANGELOG.md` for the changes made since.

<img style="width:300px;" src="web/images/logo_1024.png" alt="Doorman" />

# Lock activity
Each lock gets an **Activity** event entity (e.g. `event.ytterdor_activity`) fed from the Yale
event log, so the Home Assistant Activity/logbook shows *how* the door was locked or unlocked:
from inside, from outside with code or tag, by app, with the star button, auto-relock, failed
lock. The `user` attribute holds the user name Yale reports (for code/tag and app unlocks).
Door open/close comes from the door binary sensor, and plain locked/unlocked from the lock.

To limit traffic to Yale's cloud, the event log is read once at startup, right after a
lock/door status change, and every 5 minutes as a safety net (activity that leaves the status
unchanged between two 30-second polls - e.g. unlock, enter, relock - can therefore show up to
5 minutes late; the `yale_time` attribute holds the real time). Use the `event_type`
attribute in automations, e.g. trigger on the entity's state changing and check
`trigger.to_state.attributes.event_type == 'unlocked_outside'`.

# Debug logging
The integration has detailed debug logging to help diagnose connection issues with the Yale smarthub
(e.g. entities going `unavailable`). To enable it, add this to `configuration.yaml` and restart
Home Assistant:

```yaml
logger:
  default: info
  logs:
    custom_components.yale_doorman_via_smarthub: debug
```

Then check **Settings > System > Logs** (or `home-assistant.log`) for lines from
`custom_components.yale_doorman_via_smarthub`. Look for:
- `hub.login file not found` - the bundled auth file is missing/unreadable.
- `Login failed` / `HTTP 401` or `403` on the `/o/token/` request - bad username/password or Yale
  has rotated the API credentials this integration relies on.
- `Timeout` or `Error fetching information` - the `mob.yalehomesystem.co.uk` backend isn't
  reachable from your network, or Yale's API is down.
- `HTTP 5xx` with a response body - Yale's backend is erroring server-side.

# Thank You
Give credit to the original author, Joakim Syk ([@jockesyk](https://github.com/jockesyk)),
who created this integration - if it is useful to you, consider buying him a coffee:

<a href="https://www.buymeacoffee.com/jockesyk" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/black_img.png" alt="Buy Me A Coffee" style="height: auto !important;width: auto !important;" ></a><br>