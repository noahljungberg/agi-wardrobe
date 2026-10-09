# Render: images

Status: complete

## Purpose

All image output: cached thumbnails, the numbered **contact sheet** that lets
the model see many items in one image, the phone-friendly **outfit collage**
(1080 px wide), and data URIs for the outfit card. Also opens any photo the
user has (EXIF rotation, PNG transparency, iPhone HEIC).

## Public API

- `open_image(path | BytesIO) -> PIL.Image` (RGB; HEIC via `pillow_heif`)
- `Renderer(cache_dir)`
  - `thumbnail(path, size)`, `thumbnail_jpeg(path, size, quality)`: cached by
    path + mtime + size.
  - `data_uri(path, size=360)`
  - `contact_sheet(entries: [(label, Item)], cols=5, cell=190) -> JPEG bytes`
    (at most 40 entries)
  - `collage(items, title, subtitle, note) -> Path` (under `cache/renders/`)
  - `scaled_jpeg(path, max_width, quality) -> bytes`
- `font(size, weight)`: DejaVu or Noto if installed, else Pillow's default.

## Implementation files

- `src/wardrobe/render.py`

## Dependencies

- Allowed: `catalog` (`Item`), `PIL`, `pillow_heif`.
- Forbidden: `state` (callers register render tokens), network, `server`.

## Constraints

- A missing or broken photo draws "no photo yet" / "photo error". It never
  raises.
- Colours `BG`, `TILE`, `INK`, `MUTED` match the outfit card
  ([outfit-card.md](outfit-card.md)). Change both together.
- The collage file name is a hash of its content, so re-rendering the same
  outfit reuses the file.

## Tests

- `tests/test_render.py`: contact sheet size and decoding, collage dimensions,
  missing photo, HEIC/PNG opening.
- `tests/test_server.py`, `tests/test_http.py`: images served end to end.

## Non-goals

- No background removal yet (listed in known issues as a later improvement).
- No layout engine: a two-column grid only.
