# Changelog

All notable changes to this fork are documented here. Upstream is
[jockesyk/homeassistant-yale-doorman-via-smarthub](https://github.com/jockesyk/homeassistant-yale-doorman-via-smarthub).

## 0.0.16 (this fork)
### Changed
- The door binary sensor now defaults to **enabled**. New installs get it ticked by
  default in the setup form, and existing entries that predate the option (no
  `enable_binary_sensor` key stored) now load it too. Entries where it was explicitly
  turned **off** keep it off. Previously the option defaulted to off, so the binary
  sensor silently never appeared unless the user knew to enable it in Configure.

## 0.0.15 (this fork)
Fix the options ("Configure") dialog failing to open.

### Fixed
- Opening **Configure** raised `500 Internal Server Error` ("Config flow could not be
  loaded") on recent Home Assistant. The options flow set `self.config_entry` in its
  `__init__`, but HA now exposes `config_entry` as a read-only property on `OptionsFlow`
  and populates it itself - assigning to it raises. Removed the custom `__init__`; the
  flow now uses the framework-provided `self.config_entry` and merges submitted fields
  over the existing entry data. Without this the "enable binary sensor" option (and
  username/password/pincode) could not be changed at all.

## 0.0.14 (this fork)
Fix the integration failing to start on recent Home Assistant / Python 3.14.

### Fixed
- Authentication read `hub.login` with a synchronous `open()` + `pickle.load()`
  directly on the event loop. Recent Home Assistant traps blocking I/O on the loop,
  so the first coordinator refresh aborted, `last_update_success` was `False`, and
  `async_setup_entry` raised `ConfigEntryNotReady` - meaning **no** platform loaded
  (binary sensor and lock both failed to start). The file is now read via
  `hass.async_add_executor_job` and cached (it never changes at runtime, so this also
  removes a disk read from every 30-second poll). The API client now takes `hass`.
- The `download_yale_event_log` service read its translations file with a blocking
  `open()` on the event loop as well - it would have hit the same trap whenever the
  service ran. Moved to an executor.

## 0.0.13 (this fork)
Follow-up bug-fix pass over the whole integration.

### Fixed
- `download_yale_event_log` service only formatted the *last* fetched page's events
  instead of all pages requested via `pages: N` (`all_events` was collected but never
  used).
- Event IDs 1301-1398 were never matched in `download_yale_event_log` because the
  code compared a string (`event_id`) against a `range()` of ints, which is always
  false. These events always fell through to the wrong, more verbose format.
- `lock.code_format` returned the invalid regex `"%d{6}"` (a literal `%` followed by
  6 `d`s) instead of a real 6-digit pattern, so HA could never validate a typed code.
- `lock.async_unlock` ignored any code typed into the Lock card's UI and always used
  the PIN stored in config - now it prefers the user-supplied code and falls back to
  the configured PIN.
- `entity.unique_id`/`name` referenced `self.old_unique_id`/`self.old_name` as a
  fallback without ever initializing them, so a transient failure on the *first*
  access raised an uncaught `AttributeError` instead of degrading gracefully.
- `lock.py`/`binary_sensor.py` `async_setup_entry` made a redundant live
  `async_status()` call instead of reusing already-fetched `coordinator.data`; a
  transient hiccup on that extra call silently produced zero entities.
- `binary_sensor.disabled_by` returned the raw string `"integration"` instead of
  `RegistryEntryDisabler.INTEGRATION`.
- The options flow mutated `config_entry.data` directly, which doesn't reliably
  persist or notify listeners - now uses
  `hass.config_entries.async_update_entry(...)`, which also lets the existing update
  listener handle reloading (the old dead reload-branch code, which only had `pass`
  statements, was removed).

## 0.0.12 (this fork)
Base: upstream `main` at commit `6d883a1` (manifest version `0.0.8`).

Versioned `0.0.12` instead of `0.0.9` because GitHub's fork operation copies all of
upstream's existing tags (`v0.0.1`-`v0.0.11`) along with the repo, so those numbers
were already taken by unrelated upstream commits on this fork. `0.0.12` is the first
number with no collision.

### Added
- Debug-level logging throughout `api.py` for every request: method, URL, HTTP status
  code, and response body on failure.
- Clear, distinct log messages for login failures vs. status-fetch failures vs.
  unexpected errors, including tracebacks (`exc_info=True`) on unexpected exceptions.
- Explicit handling and logging when the bundled `hub.login` auth file is missing or
  unreadable, instead of an unhandled `FileNotFoundError`.
- README section explaining how to enable debug logging and what specific log
  messages indicate (missing auth file, bad credentials/rotated API client, network
  unreachable, server error).

### Fixed
- `async_login` referenced `self._access_token` before it was ever initialized,
  causing a silently-swallowed `AttributeError` on first login. Token state is now
  initialized in `__init__`.
- `async_status`, `async_lock`, and `async_unlock` no longer attempt to read
  `result["code"]` on a `None` response from a failed request (would raise
  `TypeError`, previously masked by broad exception handling).
- Coordinator (`_async_update_data`) now raises `UpdateFailed` with a real message
  when the API returns no data, instead of returning `None` silently.

No upstream code changes were pulled in beyond this base — the upstream `fix/*`,
`feature/*`, and `info/*` branches were checked and are all already merged into
`main`; nothing new to bring in from them.
