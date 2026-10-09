# Link importer

Status: complete. Parsers are tested on fixtures shaped like Mango and Zalando
pages; **not yet run against live shop pages** (they block datacenter IPs).

## Purpose

Turns a product link into an item folder: product photos (up to 3), name,
brand, colour, material, price, plus heuristic attributes. The item is marked
`needs_review: true`. It runs from the home connection; page data can also
arrive pre-extracted from the iPhone share sheet, which avoids bot blocking.

## Public API

- `import_url(catalog, url, payload=None, chromium=None, extra=None) -> ImportResult(url, item, error, existing)`
  - deduplicates by `normalise_url` against existing `source_url`s;
  - `payload` = the share-sheet JSON `{url, title, jsonld[], meta{}, images[]}`.
- `fetch_html(url, chromium)`: plain `httpx` with browser headers, then
  headless Chromium (Playwright, optional extra) if blocked or there's no
  product data.
- `parse_product(html, url) -> ProductInfo`, `extract_parts`, `parse_parts`,
  `parts_from_payload`.
- `download_images(urls, referer, dest, limit=3)`: skips images < 200 px; saves
  JPEG ≤ 1600 px.
- `normalise_url(url)`: keeps only `c`, `color`, `colour`, `size` query params.
- `image_bytes_to_jpeg(data)`: used by the inbox upload route.

## Implementation files

- `src/wardrobe/importer.py`

## Dependencies

- Allowed: `catalog`, `heuristics`, `render.open_image`, `httpx`, `PIL`,
  `playwright` (lazy import).
- Forbidden: `state`, `server`.

## Constraints

- Parsing order: JSON-LD `Product`/`ProductGroup` (walking `@graph`,
  `hasVariant`), then OpenGraph/product meta, then `<title>`, then `<img>`.
- Shop specifics:
  - **Mango**: the colour variant is the `?c=NN` query parameter. Pick the
    JSON-LD variant and the images whose path contains `_NN`.
  - **Zalando**: rewrite `img01.ztat.net` image URLs to
    `imwidth=1200&filter=packshot`.
- `material` holds the fabric type the heuristics recognise (corduroy, wool);
  the page's raw composition goes to `composition`.
- At most 25 links per `import_links` tool call (keeps tool latency sane).

## Tests

- `tests/test_importer.py`: Mango variant by colour code, Zalando OpenGraph,
  URL normalisation, share-sheet payload import with download mocked, dedupe,
  fetch error reporting.

## Non-goals

- No logging into shop accounts, no scraping of order history, no email
  parsing (dropped in the design discussion).
- No per-shop scraper zoo: add a shop-specific rule only when JSON-LD/OG aren't
  enough (see the `add-shop-parser` skill).
