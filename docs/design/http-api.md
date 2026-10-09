# HTTP apps and routes

Status: complete

## Purpose

The two Starlette apps that `wardrobe serve` runs: the **public** app (MCP,
OAuth, images), exposed by Tailscale Funnel, and the **private** app (iPhone
Shortcuts), reachable only inside the tailnet.

## Public API

Public app, `build_public_app(w, mcp)` on `WARDROBE_PUBLIC_PORT` (8765):

| Route | Auth | Purpose |
|---|---|---|
| `POST /mcp` | OAuth bearer | MCP, stateless, JSON responses |
| `/.well-known/oauth-*`, `/register`, `/authorize`, `/token`, `/revoke` | per OAuth spec | from the SDK |
| `GET/POST /login` | passphrase | [auth.md](auth.md) |
| `GET /img/r/{token}.jpg` | random token, 24 h | rendered collages |
| `GET /img/i/{item_id}/{size}?exp&sig` | HMAC signature, 7 days | item photos (sizes 240/420/600/900) |
| `GET /` | none | plain-text hello |

Private app, `build_private_app(w)` on `WARDROBE_PRIVATE_PORT` (8766). Every
route except `/health` requires `Authorization: Bearer $WARDROBE_DEVICE_TOKEN`
(or `?token=`) when that variable is set:

| Route | Body | Purpose |
|---|---|---|
| `POST/GET /location` | `{lat|latitude, lon|longitude, name|city?, tz?}` | latest phone location |
| `POST /import` | `{url}` or share-sheet `{url, title, jsonld[], meta{}, images[]}` | link import → `{ok, id, message}` |
| `POST /inbox` | multipart, any file fields | photos → `inbox/` as JPEG |
| `GET /health` | none | `{ok, items, errors}` |

Bodies without a form content type are parsed as JSON. Shortcuts sometimes
omit the header.

## Implementation files

- `src/wardrobe/server.py`: `build_public_app`, `build_private_app`, `_body`,
  and the `custom_route` handlers inside `build_mcp`.

## Dependencies

- Allowed: `starlette`, `mcp` transport security, `importer` (import/inbox),
  `state`, `catalog`.
- Forbidden: putting location or upload routes on the public app.

## Constraints

- Host/Origin checks (DNS rebinding protection) allow the Funnel host,
  `127.0.0.1:<port>` and `localhost:<port>`. Origins also allow
  `https://chatgpt.com` and `https://claude.ai`.
- uvicorn trusts `X-Forwarded-*` only from `127.0.0.1` (Tailscale's local proxy).
- Public custom routes are unauthenticated by design. Never expose a file path
  or listing there.
- Upload parts are limited to 40 MB each.

## Tests

- `tests/test_http.py`: real uvicorn servers on free ports. OAuth + MCP,
  collage/item images (valid, tampered, unknown), `/location` with and without
  the token, `/inbox` upload, `/health`.

## Non-goals

- No web UI beyond the login page. The owner doesn't want websites.
