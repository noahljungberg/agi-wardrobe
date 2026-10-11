# Web UI: the wardrobe in a browser

Status: complete (2026-10-11). Verified in Chromium; not yet used by the owner.

## Purpose

A page for a computer on the tailnet, at `https://<machine>.<tailnet>.ts.net:8443/ui`,
for things that are clumsy in chat:

- **Browse everything** with photos, grouped by slot, with search.
- **See what's available**: owned vs. in the laundry vs. retired vs. wishlist.
- **See what's missing**:
  - gaps in the wardrobe (Insights);
  - things the catalogue is incomplete about ("To complete", "No photo").
- **Fix things quickly**: status, favourite, details, aliases, photos; quick-add
  an item by name, or add one from a link or an inbox photo.
- **Tell the stylist how you look** (Me tab): photos of you plus hair, eyes,
  skin, undertone, height, build and fit notes, with a live preview of what the
  AI reads and a switch for sending your photo with suggestions.
- **Hand work to the assistant**: "Copy brief" / "Copy request" produce text to
  paste into ChatGPT/Claude, which then uses the MCP tools.

## Public API

`WebUI(catalog, state, renderer, config, today)`, whose `.routes()` are mounted
on the private app (`server.build_private_app`):

| Route | Auth | Purpose |
|---|---|---|
| `GET /` | none | redirect to `/ui` |
| `GET /ui` | session cookie | the page (`ui/catalog.html`), or the login page |
| `POST /ui/login`, `POST /ui/logout` | passphrase | sets/clears an HMAC-signed `wardrobe_ui` cookie (30 days, HttpOnly, SameSite=Strict) |
| `GET /ui/api/items` | cookie | all items (all statuses) + inbox file names + categories/statuses |
| `GET /ui/api/analysis` | cookie | `analysis.analyse` output |
| `POST /ui/api/items` | cookie + `X-Wardrobe: 1` | create (quick add, wishlist, or from inbox photos) |
| `PATCH /ui/api/items/{id}` | cookie + header | edit fields; `needs_review: false` clears the flag |
| `POST /ui/api/items/{id}/photos` | cookie + header | multipart photo upload (converted to JPEG) |
| `POST /ui/api/import` | cookie + header | link import via `importer.import_url` |
| `GET /ui/photo/{id}/{n}/{size}` | cookie | item photo thumbnail (240/480/960) |
| `GET /ui/inbox/{name}/{size}` | cookie | inbox photo thumbnail |
| `GET`/`PATCH /ui/api/me` | cookie (+ header for PATCH) | appearance fields (`APPEARANCE_FIELDS`; height 100–250 cm) and photo names |
| `POST /ui/api/me/photos`, `POST /ui/api/me/from-inbox`, `DELETE /ui/api/me/photos/{name}` | cookie + header | add/remove photos of the user |
| `GET /ui/me/{name}/{size}` | cookie | photo of the user (`no-store`) |

Item JSON: `id, name, category, slot, status, favourite, rain_ok, aliases,
needs_review, photos (count), wears, last_worn, guessed[]`, plus `brand type
colour material warmth formality size price currency source_url notes bought`
when set.

## Implementation files

- `src/wardrobe/webui.py`: `WebUI` (session, API handlers, routes),
  `_clean_fields` (input validation), and the login page.
- `src/wardrobe/ui/catalog.html`: the whole front end. One self-contained
  file of HTML, CSS and vanilla JS, with no build step and no external requests.

## Dependencies

- Allowed: `catalog`, `state`, `render`, `analysis`, `importer`, `outfit`
  (`slot_of`), `config`, `starlette`. `today` is injected by `server`
  (`Wardrobe.local_today`).
- Forbidden: `server` (it's a higher layer); writing the folder other than via
  `Catalog.save_item`; any route on the **public** app.

## Constraints

- **Private app only.** It's never reachable through Funnel.
- Login secret = `WARDROBE_PASSPHRASE`, else `WARDROBE_DEVICE_TOKEN`, else
  none (open; local dev only). Ten wrong attempts in 15 minutes block login.
- Every write needs the `X-Wardrobe: 1` header (CSRF defence on top of
  SameSite=Strict).
- Only fields in `EDITABLE` are accepted. Category and status must be known,
  warmth must be 0–5, formality 1–5, and a name can't be emptied.
- Inbox file names must match `SAFE_NAME` (no paths).
- Quick-added owned items get `needs_review: true`, so they appear under
  "To complete" and in the brief for the assistant. Wishlist items don't.
- "To complete" counts only items you own (owned or laundry), not wishlist or
  retired.
- Colours shown are the canonical ones from `heuristics._COLOURS`. The hex map
  lives in `catalog.html` (`COLOURS`); keep the names in sync.
- The gap checklist in Insights is computed client-side from
  `analysis.coverage` and `per_slot` (`gapList` in `catalog.html`).

## Tests

- `tests/test_webui.py`:
  - login gate (page, API and photos need the cookie);
  - open mode and the root redirect;
  - edits write `item.yaml` (status, favourite, aliases); laundry items leave
    suggestions; invalid input is rejected; the CSRF header is required;
  - quick add, wishlist and review;
  - the Me API: auth, CSRF, validation, photo upload, from inbox, delete, traversal;
  - photo upload/serve/bounds, inbox listing, inbox traversal rejected,
    create from an inbox photo;
  - import (importer mocked); analysis.
- `test_browse_edit_and_add_in_a_browser` (Chromium):
  - the grid renders 16 cards;
  - the drawer sets laundry, which is written to the folder and hidden from
    "Available now";
  - quick add opens the new item;
  - Insights renders;
  - the Me form previews and saves `me/about.yaml`;
  - no JS errors.

## Non-goals

- Not a shop or a recommendation engine. Gaps produce a wishlist entry or a
  prompt for the assistant.
- No pairing or outfit builder here yet. Pairing with an image model is a
  noted future idea.
- No multi-user support and no public exposure.
