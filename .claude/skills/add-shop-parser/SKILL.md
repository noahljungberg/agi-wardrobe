---
name: add-shop-parser
description: Make product links from a specific shop import correctly (name, colour, photos) in importer.py. Use when `wardrobe import` or the import_links tool fails or gets wrong data for a shop such as Mango, Zalando, Levi's, BestSecret, Arket or COS.
---

# Fix or add a shop in the link importer

Read first: [docs/design/importer.md](../../../docs/design/importer.md).

## Steps

1. **Get real HTML.** Shops block cloud IPs, so the owner runs this on the home
   machine:
   `curl -sL -A "Mozilla/5.0" "<url>" > page.html`, or saves the page from a
   browser. Check that the file contains the product name.
2. **Strip personal data**: no cookies, account names, addresses or order
   numbers. Keep only `<head>` (meta + `application/ld+json`) and the product
   image tags. Save it as `tests/fixtures/<shop>-<product>.html`.
3. **See what generic parsing gets:**
   `uv run python -c "from wardrobe.importer import parse_product; print(parse_product(open('tests/fixtures/X.html').read(), '<url>'))"`.
4. **Fix with the smallest rule**, in this order of preference:
   1. generic JSON-LD/OpenGraph handling that would help other shops too;
   2. a URL/variant rule in `_colour_code` or `_pick_images` (like Mango `?c=NN`
      or Zalando `imwidth`);
   3. only then a shop-specific branch, keyed on the host, with a comment that
      says why.
5. **Test** in `tests/test_importer.py`: parse the fixture and assert name,
   brand, colour and that the images are the right variant.
6. If the page is JavaScript-only, check that the Playwright fallback
   (`fetch_html`) gets the data; otherwise document the share-sheet route for
   that shop in [docs/guides/shortcuts.md](../../../docs/guides/shortcuts.md).
7. Update the shop notes in `docs/design/importer.md`, and the importer row in
   `docs/QUALITY.md` if trust changed. Run `scripts/verify.sh`.

## Don't

- Don't add login or cookie handling for shop accounts (a non-goal).
- Don't commit full pages with tracking scripts or personal data.
