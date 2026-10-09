# MCP tools and the `Wardrobe` service

Status: complete

## Purpose

The surface the chat model sees: server instructions plus 11 tools. Also the
`Wardrobe` service object that tools and HTTP routes share.

## Public API

Server instructions: `INSTRUCTIONS` in `server.py` (how to behave: call
`dress_me` first, always `show_outfit`, log silently, phone-short replies, at
most one question).

| Tool | R/O | Inputs | Returns |
|---|---|---|---|
| `dress_me` | yes | `wearing[]?`, `occasion?`, `place?`, `day` today/tomorrow | Weather + source, guidance, anchors (A1…), candidates per slot (#1…), profile, preferences, recent outfits; **contact sheet image** |
| `show_outfit` | yes | `item_ids[]`, `title?`, `note?`, `day` | Text with collage link, collage image (640 px), `structuredContent` for the card, `_meta.wardrobe/thumbs`; bound to `ui://wardrobe/outfit-v2.html` |
| `log_wear` | no | `items[]` (ids or phrases), `day` today/yesterday/ISO, `note?` | Confirmation; ambiguous phrases are listed, not logged |
| `find_items` | yes | `query`, `category?`, `include_retired` | Up to 40 matches with wear stats; contact sheet |
| `save_item` | no | `item_id?` + any item fields, `status`, `from_inbox[]` | Saved summary + photo; clears `needs_review` |
| `review_inbox` | yes | none | Up to 6 inbox photos, each with its file name |
| `import_links` | no (open world) | `urls[]` (≤25) | Per-link result; contact sheet of new items |
| `wardrobe_analysis` | yes | none | JSON from `analysis.analyse` + profile + preferences |
| `remember` | no | `note` | Preference id |
| `forget` | no (destructive) | `pref_id` | Confirmation |
| `set_location` | no | `place` | Confirmation (geocoded) |

`Wardrobe` service (`Wardrobe(config, weather=None)`):

- `catalog`, `state`, `renderer`, `weather`, `config`
- `place(override) -> (Place, source)`: priority explicit place → phone
  location < 36 h → profile `home` → `WARDROBE_HOME` → last known location;
  raises `LocationUnknown`.
- `local_today(place=None)`: the user's calendar day.
- `day_weather(place, which)`: returns `None` on failure (callers degrade).
- `item_image_url(item)` (HMAC-signed, 7 days), `verify_image`, `render_url(path)`.
- `build_mcp(w) -> MCPServer`

## Implementation files

- `src/wardrobe/server.py`: `INSTRUCTIONS`, `Wardrobe`, `build_mcp` and the
  tool functions inside it, helpers (`_item_line`, `_resolve_many`,
  `_neutral_weather`, …).

## Dependencies

- Allowed: every `wardrobe` module below layer 4, `mcp`, `mcp_types`,
  `pydantic`, `starlette`, `httpx` (exception types only).
- Forbidden: `cli`, `demo`.

## Constraints

- `@apps.tool` and `apps.add_html_resource` must run **before**
  `MCPServer(...)` is constructed, or the tool silently disappears.
- `readOnlyHint` must be honest. ChatGPT asks for confirmation on every write
  tool, so keep writes few and obvious.
- Tool text is compact and puts ids in backticks; one image per result.
- User mistakes come back as text or `is_error`, never as exceptions
  ([CONVENTIONS.md](../../CONVENTIONS.md)).
- `check_docs.py` fails if a tool in `server.py` is missing from the table
  above.

## Tests

- `tests/test_server.py`: in-process `Client(build_mcp(w))` with
  `FakeWeather`: tool list and annotations, `dress_me` (home/phone location,
  anchors, no location), `show_outfit` payloads, logging and ambiguity, inbox
  → `save_item`, preferences, analysis, `set_location`, geocoder outage.
- `tests/test_http.py`: the same tools over real HTTP with OAuth.

## Non-goals

- No MCP prompts or resources other than the card.
- No sampling or elicitation: the chat model drives the conversation.
