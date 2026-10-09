# AGI Wardrobe — Design

A personal wardrobe assistant that lives inside the chat app you already use
(ChatGPT first, Claude optional). You say what you're wearing or ask what to
wear; it knows your clothes (with pictures), where you are and the weather,
and answers in one message. No website, no daily chores.

Status: **design agreed in discussion, not built yet.** Open questions are at
the bottom.

## Principles

1. **Zero daily effort.** Nothing is required of you day to day. You ask when you want something.
2. **Pictures first.** Every item has at least one photo. The AI *looks* at the
   clothes when styling, and you see the outfit as an image.
3. **The folder is the truth.** Your wardrobe is a plain folder of photos and
   small YAML files that you own and can edit by hand. The server only reads
   it (plus writes metadata when asked to tag new items).
4. **Few, chunky tools.** One sentence from you should map to one or two tool
   calls.
5. **Never nag.** At most one clarifying question per conversation.

## Clients

| Client | How | Notes |
|---|---|---|
| ChatGPT (Pro Lite), web + iPhone | Custom connector via Developer mode | Primary. Plan eligibility to be verified (step 0). Tools without `readOnlyHint` ask for confirmation once per chat. |
| Claude, web + iPhone | Custom connector (added on claude.ai, then available on mobile) | Optional, same server. |
| Gemini | Custom MCP status unclear | Same server if/when supported. |

## Architecture

```
 iPhone ─ ChatGPT / Claude app
              │ (their cloud calls our server)
              ▼
   https://<box>.<tailnet>.ts.net  ── Tailscale Funnel (public, only these paths)
      /mcp           MCP server (Streamable HTTP, behind OAuth passphrase)
      /img/<token>   rendered outfit collages (unguessable, expiring)
              │
 ┌────────────┴───────────── home device (Docker) ─────────────────────┐
 │  MCP server (Python, official MCP SDK)                               │
 │  ├─ wardrobe index  ← watches $WARDROBE_DIR (photos + item.yaml)     │
 │  ├─ link importer   ← product URLs → photos + prefilled item.yaml    │
 │  ├─ weather         ← Open-Meteo (free, no key)                      │
 │  ├─ collage render  ← Pillow (+ optional rembg background removal)   │
 │  └─ state (SQLite)  ← $WARDROBE_STATE: wear log, prefs, last location│
 │                                                                      │
 │  Tailnet-only (NOT funneled):                                        │
 │      /location   ← iOS Shortcut posts current position               │
 │      /import     ← iOS share-sheet Shortcut posts a product page     │
 └──────────────────────────────────────────────────────────────────────┘
```

Tailscale alone is not enough: ChatGPT/Claude connect from their own cloud,
so the MCP endpoint must be publicly reachable. Funnel exposes only `/mcp` and
`/img`; everything that touches location or imports stays tailnet-only.

## The wardrobe folder

```
$WARDROBE_DIR/
├── items/
│   ├── mango-corduroy-trousers-beige/
│   │   ├── item.yaml
│   │   ├── 1.jpg            # main photo (packshot or your own)
│   │   └── 2.jpg            # optional extra angles
│   └── ...
├── links.txt                # product URLs to import (one per line)
├── inbox/                   # drop your own photos here to add items
└── profile.yaml             # sizes, style notes, dislikes, "I run cold", home city
```

`item.yaml` — only `name` and a photo are required; everything else can be
filled in by the importer or by the assistant:

```yaml
name: Corduroy trousers, regular fit
brand: Mango
aliases: [beige cords, manchester trousers, manchesterbyxa]
category: bottoms            # tops | bottoms | outerwear | shoes | accessories | ...
colour: beige
pattern: solid
material: cotton corduroy
warmth: 3                    # 1 summer … 5 deep winter
formality: 2                 # 1 gym … 5 suit
rain_ok: false
size: "42"
bought: 2026-01-23
source_url: https://shop.mango.com/...
status: owned                # owned | retired
notes: ""
```

Runtime state (wear log, learned preferences, last location, rendered
collages) lives in `$WARDROBE_STATE`, never in your folder.

## Getting clothes in

1. **Links (main path).** You collect product links for what you own (with
   the right colour selected). Either paste them into `links.txt` or into
   the chat. The importer, per link:
   - opens the page with headless Chromium from the home connection
     (retail sites block datacenter IPs);
   - reads JSON-LD `Product` / OpenGraph data plus small per-site parsers
     (Mango product id + colour code, Zalando SKU);
   - downloads 1–3 packshot images and writes a prefilled `item.yaml`;
   - reports back in chat with thumbnails: "Imported 14, 2 failed".
2. **Share sheet (fallback for blocked pages).** In Safari on the product
   page: Share → "Add to wardrobe". The Shortcut runs JavaScript on the page
   *in your own browser* to grab title, colour and image URLs, and posts them
   to `/import` over Tailscale.
3. **Photos (for things with no link).** Drop a photo in `inbox/`. Next time
   you chat, the assistant sees it, proposes the metadata, and saves it after
   one "yes". Optional background removal makes own photos match packshots.

Seed: links already found in old order emails (Mango, Zalando) can be put in
`links.txt` as a head start.

## Location and weather

- An iOS personal automation ("when ChatGPT is opened" → Get Current
  Location → POST `/location` over Tailscale) keeps the last known position
  fresh with no manual step. Only the latest position is stored.
- Saying "I'm in SF" in chat overrides it.
- Open-Meteo hourly forecast for the hours you're out (temperature,
  feels-like, precipitation probability, wind), not just "now".

## MCP tools

| Tool | Read-only? | Purpose |
|---|---|---|
| `dress_me(anchor?, occasion?, location?)` | yes | Resolves fuzzy anchor items ("beige cords"), gets location + weather, returns weather-appropriate candidates (skipping recently worn) **with thumbnails** so the model can see them. |
| `show_outfit(item_ids, caption?)` | yes | Renders the outfit: MCP Apps card + image content + collage link. |
| `log_wear(items, date?)` | no | Records what you wore. Called when you say you're wearing something. |
| `find_items(query)` | yes | "Do I have a navy knit?" — returns matches with thumbnails. |
| `import_links(urls)` | no | Runs the link importer. |
| `review_inbox()` / `save_item(...)` | no / no | Tag new photos from `inbox/`; edit item metadata. |
| `wardrobe_analysis()` | yes | Counts by category/colour/warmth/formality, never-worn, cost-per-wear, orphans (pair with little), near-duplicates, coverage vs. the climates you've been in. The model turns this into gap advice. |
| `remember(preference)` | no | "I hate black with brown." |

Server-level instructions tell the model: check weather before suggesting,
always show the outfit, log wear silently when the user says what they're
wearing, keep answers phone-short, at most one question.

## Showing the outfit

Clients differ in what they render, so `show_outfit` returns all of:

- **A. MCP Apps UI resource** — inline outfit card (photos + weather). Best
  experience; confirmed on ChatGPT and Claude web/desktop, iPhone to verify.
- **B. Image content** — the model sees it; Claude shows it inside the
  collapsed tool block.
- **C. Collage link** — one PNG (outerwear / top / bottom / shoes + weather
  strip) at `/img/<token>`, expiring after 24 h. Tap → full-screen image.
  Works everywhere.

## Security

- Funnel exposes only `/mcp` and `/img`.
- `/mcp` requires OAuth (single user, passphrase login shown once when adding
  the connector).
- Collage URLs are random, unguessable and expire.
- Location and import endpoints are reachable only inside the tailnet.
- Only the latest location is stored; no movement history.

## Build plan

0. **Spike (≈1 h).** Minimal server behind Funnel with a fake `show_outfit`
   returning A + B + C. Verify on iPhone: Developer mode available on Pro
   Lite? write tools allowed? which display methods render?
1. Folder format, index + file watcher, `find_items`, `show_outfit`
   (collage renderer).
2. Link importer (headless Chromium + JSON-LD/OG + Mango/Zalando parsers),
   `import_links`, `links.txt`.
3. Weather + location Shortcut, `dress_me`, `log_wear`, server instructions.
4. Inbox tagging, background removal, `wardrobe_analysis`, `remember`.
5. Later: trip packing lists ("SF for 5 days"), Claude connector.

## Open questions

- Home device: OS / always on? (decides Docker vs native, Chromium setup)
- How photos reach `inbox/` from the iPhone (Syncthing, SMB over Tailscale,
  iCloud Drive on a Mac).
- Where the seed folder should live (keep personal data out of this code repo).
