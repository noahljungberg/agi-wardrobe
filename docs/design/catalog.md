# Catalog: the wardrobe folder

Status: complete

## Purpose

Owns the user's wardrobe folder (`$WARDROBE_DIR`): reading `items/<id>/item.yaml`
plus photos into `Item` objects, `profile.yaml`, `me/` (how the user looks:
`about.yaml` and photos), the `inbox/`, and every write to that folder. The folder is the source of truth and must stay hand-editable.
The user-facing format is in [guides/wardrobe-folder.md](../guides/wardrobe-folder.md).

## Public API

- `Catalog(root, refresh_interval=2.0)`
  - `ensure_layout()`: create `items/` and `inbox/`.
  - `items(include_inactive=False) -> list[Item]`: active means status `owned`
    (or unset).
  - `get(item_id) -> Item | None`, `profile() -> dict`, `inbox_files() -> list[Path]`.
  - `refresh(force=False)`: re-reads only if file names or mtimes changed;
    checks at most every `refresh_interval` seconds.
  - `save_item(item_id | None, fields, add_photos=None, move_photos=True, archive_photos=None) -> Item`:
    creates (when `item_id` is None, which needs `name`) or merges fields. A
    field set to `None` is deleted. Photos are moved in as `<n>.<ext>`.
    `archive_photos` accepts explicit existing direct-child image `Path`s (for
    example from `Item.photos`), moving only those files to `.photo-archive/`.
    Archived originals are preserved but not scanned/displayed; collisions get
    a numeric suffix. May be combined with replacement `add_photos`, or used
    alone. Invalid archive targets, archive directories, or replacement paths
    fail before any writes; traversal and symlinks are rejected. This is not a
    filesystem transaction: later I/O failures may leave a partial operation.
  - `new_item_id(name, brand, colour) -> str`; `errors: list[str]` (broken files).
- `Item`: `id`, `path`, `data`, `photos`, `inferred` (fields guessed, not written)
  - properties: `name brand category layer colour warmth formality rain_ok
    status active aliases main_photo`
  - `label()`: "Mango Corduroy trousers (beige)"; `summary()`: compact dict for tool output.
- `load_item(folder)`, `write_item_yaml(path, data)`, `slugify(text)`.
- Constants: `IMAGE_EXTS`, `STATUSES` (`owned`, `laundry`, `retired`,
  `wishlist`), `ACTIVE_STATUSES` (only `owned` is suggested), `FIELD_ORDER`
  (key order in written YAML).
- `Item.favourite`: the `favourite: true` flag.
- `me() -> dict`: the `APPEARANCE_FIELDS` from `me/about.yaml` plus `photos` (paths).
  `save_me(fields, add_photos)` merges (None removes) and rejects unknown fields;
  `remove_me_photo(name)` only accepts plain file names.

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
  inbox photo, broken YAML isolation, retired items hidden; `me/` appearance
  and photos. Explicit photo archival covers preservation, replacement, repeat
  collisions, refresh, and no writes on invalid paths.
- Indirectly: every tool test uses the demo catalog.

## Non-goals

- No database for items. No item history or versioning (use git on the folder
  if wanted).
- No image processing here (that's `render`) and no network (that's `importer`).
