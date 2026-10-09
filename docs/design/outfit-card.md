# Outfit card (MCP App view)

Status: complete. Verified in Chromium against both host protocols; not yet
seen on the iPhone apps.

## Purpose

The inline card ChatGPT/Claude render under `show_outfit`: title, weather line,
a grid of item photos with name and brand · colour, the note, and an
"Open full image" button for the collage.

## Public API

- Resource `ui://wardrobe/outfit.html`, MIME `text/html;profile=mcp-app` (MCP
  Apps), registered with `_meta.ui.csp.resourceDomains = [public_url]`.
- Resource `ui://wardrobe/outfit-openai.html`, MIME `text/html+skybridge` (same
  HTML, for ChatGPT's `openai/outputTemplate`).
- Input it renders:
  - `structuredContent = {title, weather, note, collage_url, items: [{id, name, brand, colour, category, image}]}`
  - `_meta["wardrobe/thumbs"] = {item_id: data URI}`. The card prefers these
    and falls back to `image` URLs.

## Implementation files

- `src/wardrobe/ui/outfit.html`: self-contained HTML/CSS/JS, no build step, no
  external scripts.
- Registered in `src/wardrobe/server.py` (`build_mcp`, before `MCPServer(...)`
  is constructed).

## Dependencies

- Two host runtimes, both supported:
  1. **MCP Apps bridge** (JSON-RPC over `postMessage`): sends `ui/initialize`
     (protocolVersion `2026-01-26`) and then `ui/notifications/initialized`;
     handles `ui/notifications/tool-result` and
     `ui/notifications/host-context-changed`; sends
     `ui/notifications/size-changed` and the `ui/open-link` request; answers
     unknown host requests with `{}`.
  2. **ChatGPT `window.openai`**: `toolOutput`, `toolResponseMetadata`,
     `theme`, `openExternal`, and the `openai:set_globals` event.
- No network calls of its own.

## Constraints

- Photos travel as data URIs in `_meta` (hidden from the model, no CSP domain
  needed). Keep thumbnails at about 420 px so the result stays well under 1 MB
  for ~6 items.
- Theme follows the host (`data-theme` from `hostContext.theme` or
  `openai.theme`) with `light-dark()` colours. Photo tiles stay light in dark
  mode, because product photos have white backgrounds.
- Escape all text (`esc`). Data comes from the user's YAML.

## Tests

- `tests/test_widget.py` (needs Chromium; skipped otherwise): the bridge
  handshake order, three photos rendered, dark theme applied; the
  `window.openai` path renders and `openExternal` gets the collage URL.

## Non-goals

- No interactivity beyond opening the image. Swapping items is done by talking
  to the model, not through UI calls back to tools.
