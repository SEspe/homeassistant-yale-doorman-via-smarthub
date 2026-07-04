# Changelog

All notable changes to this fork are documented here. Upstream is
[jockesyk/homeassistant-yale-doorman-via-smarthub](https://github.com/jockesyk/homeassistant-yale-doorman-via-smarthub).

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
