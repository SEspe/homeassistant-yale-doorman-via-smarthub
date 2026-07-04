# Changelog

All notable changes to this fork are documented here. Upstream is
[jockesyk/homeassistant-yale-doorman-via-smarthub](https://github.com/jockesyk/homeassistant-yale-doorman-via-smarthub).

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
