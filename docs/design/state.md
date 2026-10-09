# State: runtime data in SQLite

Status: complete

## Purpose

Everything the server learns or issues, kept apart from the user's folder: wear
log, remembered preferences, the latest location, OAuth clients/codes/tokens,
render tokens, and generated secrets. Also owns the cache directory.

## Public API

`State(state_dir)` (creates `state.db` and `cache/`):

- wear log: `log_wear(item_ids, day, place, temp_min, temp_max, note) -> outfit_id`
  (re-logging an item for the same day replaces it), `last_worn()`,
  `wear_counts()`, `recent_outfits(since)`, `wear_history()`
- preferences: `add_pref(text) -> id`, `remove_pref(id)`, `prefs()`
- location: `set_location(lat, lon, name, source, tz=None)`, `location() -> Location | None`
  (`Location.age_text()`)
- OAuth key-value: `oauth_put(kind, key, data, expires_at)`, `oauth_get` (expired
  entries count as missing and are deleted), `oauth_delete`
- renders: `add_render(path, ttl=86400) -> token`, `render_path(token)`
- `secret(name)`: a random secret created once (image signing key)
- `cleanup()`: drops expired renders (and their files) and expired OAuth rows
- `cache_dir`

## Implementation files

- `src/wardrobe/state.py`: `SCHEMA`, `Location`, `State`.

## Dependencies

- Allowed: `sqlite3`, standard library.
- Forbidden: every other `wardrobe` module (layer 0). Callers pass plain values in.

## Constraints

- One connection, `check_same_thread=False`, guarded by an `RLock`; WAL mode;
  autocommit.
- The `location` table has exactly one row (`id = 1`). **Never add location
  history.**
- Schema changes: `CREATE TABLE IF NOT EXISTS` only, with no migration
  framework yet. Adding a column to an existing table needs a migration step
  (see known issues).
- OAuth `kind` values in use: `client`, `pending`, `code`, `access`, `refresh`.

## Tests

- `tests/test_state.py`: same-day re-log replaces, last worn, preferences,
  single-row location, render expiry, OAuth expiry.
- Through `tests/test_server.py` and `tests/test_http.py` (OAuth).

## Non-goals

- Not a store for items or photos (that's the folder).
- No multi-user support.
