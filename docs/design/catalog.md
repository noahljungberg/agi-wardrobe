# Catalog: the wardrobe folder

Status: complete

## Purpose

Owns the user's wardrobe folder (`$WARDROBE_DIR`): reading `items/<id>/item.yaml`
plus photos into `Item` objects, `profile.yaml`, the `inbox/`, and every write
to that folder. The folder is the source of truth and must stay hand-editable.
The user-facing format is in [guides/wardrobe-folder.md](../guides/wardrobe-folder.md).

## Public API

- `Catalog(root, refresh_interval=2.0)`
  - `ensure_layout()`: create `items/` and `inbox/`.
  - `items(include_inactive=False) -> list[Item]`: active means status `owned`
    (or unset).
  - `get(item_id) -> Item | None`, `profile() -> dict`, `inbox_files() -> list[Path]`.
  - `refresh(force=False)`: re-reads only if file names or mtimes changed;
    checks at most every `refresh_interval` seconds.
  - `save_item(item_id | None, fields, add_photos=None, move_photos=True) -> Item`:
    creates (when `item_id` is None, which needs `name`) or merges fields. A
    field set to `None` is deleted. Photos are moved in as `<n>.<ext>`.
  - `new_item_id(name, brand, colour) -> str`; `errors: list[str]` (broken files).
- `Item`: `id`, `path`, `data`, `photos`, `inferred` (fields guessed, not written)
  - properties: `name brand category layer colour warmth formality rain_ok
    status active aliases main_photo`
  - `label()`: "Mango Corduroy trousers (beige)"; `summary()`: compact dict for tool output.
- `load_item(folder)`, `write_item_yaml(path, data)`, `slugify(text)`.
- Constants: `IMAGE_EXTS`, `ACTIVE_STATUSES`, `FIELD_ORDER` (key order in written YAML).

## Implementation files

- `src/wardrobe/catalog.py`: everything above.

## Dependencies

- Allowed: `heuristics` (fills missing fields at load time), `yaml`.
- Forbidden: `state`, `server`, network, `PIL`. The catalog doesn't know about
  wear logs or rendering.

## Constraints

- Guessed fields live in memory only (`Item.inferred`); `item.yaml` gets only
  what the user, importer or `save_item` set explicitly.
- Writes are atomic (`.yaml.tmp` + replace). Item ids must resolve inside
  `items/` (no path traversal).
- One broken `item.yaml` must not break loading. Collect it in `errors`.
- Refresh is a directory scan. Fine for hundreds of items; revisit beyond
  ~2000 (see known issues).

## Tests

- `tests/test_catalog.py`: inference on load, hand edits picked up, save with
  inbox photo, broken YAML isolation, retired items hidden.
- Indirectly: every tool test uses the demo catalog.

## Non-goals

- No database for items. No item history or versioning (use git on the folder
  if wanted).
- No image processing here (that's `render`) and no network (that's `importer`).
