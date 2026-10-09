# Architecture

One Python package, `src/wardrobe/`, runs as one process (`wardrobe serve`)
that serves two HTTP apps:

```
                    Tailscale Funnel (public)                 tailscale serve (tailnet only)
ChatGPT/Claude ──► :443 ─► 127.0.0.1:8765  public app     iPhone Shortcuts ──► :8443 ─► 127.0.0.1:8766  private app
                           ├─ /mcp            MCP (OAuth)                           ├─ /location
                           ├─ /authorize /token /register /login                    ├─ /import
                           └─ /img/r/* /img/i/*  images                             ├─ /inbox
                                                                                    └─ /health
```

Both apps share one `Wardrobe` service object (`server.py`), which holds the
catalog, the state DB, the renderer and the weather client.

## Data ownership

| Data | Owner | Where | Rules |
|---|---|---|---|
| Items, photos, profile | the user | `$WARDROBE_DIR` (items/, inbox/, profile.yaml) | Source of truth, hand-editable. Only `catalog.Catalog.save_item` writes it. |
| Wear log, preferences, last location, OAuth, render tokens | the server | `$WARDROBE_STATE_DIR/state.db` (SQLite) | Only `state.State` touches SQL. |
| Thumbnails, collages | the server | `$WARDROBE_STATE_DIR/cache/` | Disposable; safe to delete. |

## Layers

A module may import only from **strictly lower** layers.
`scripts/check_architecture.py` enforces this (`LAYERS`), and
`scripts/check_docs.py` checks that every module there is named below.

| Layer | Modules | Role |
|---|---|---|
| 0 Foundation | `config`, `heuristics`, `state`, `weather` | No internal imports. Env config, name→attribute guessing, SQLite, forecasts. |
| 1 Model | `catalog` | The wardrobe folder as `Item` objects. |
| 2 Domain | `matching`, `outfit`, `render` | Pure-ish logic on items: fuzzy resolve, slot/weather scoring, images. |
| 3 Features | `analysis`, `importer`, `auth`, `demo` | Built from the domain: gap stats, link import, OAuth provider, demo data. |
| 4 App | `server` | MCP tools, HTTP routes, the `Wardrobe` service. The only place that composes everything. |
| 5 Entry | `cli` | Argument parsing, uvicorn, wiring config → server. |
| 6 Entry | `__main__` | `python -m wardrobe`. |

```
cli ─► server ─┬─► analysis ─► outfit ─► weather
               ├─► importer ─► render
               ├─► auth ─► state
               ├─► matching ─┐
               └────────────►├─► catalog ─► heuristics
                             └─ (all of layer 2–3 may use catalog/heuristics)
```

## Third-party boundaries

Also enforced by `scripts/check_architecture.py` (`THIRD_PARTY`).

| Package | Allowed in | Why |
|---|---|---|
| `mcp`, `starlette` | `server`, `auth` | Protocol and HTTP stay at the edge; domain code is testable without them. |
| `mcp_types` | `server` | Tool schemas and results. |
| `pydantic` | `server`, `auth` | Tool parameter schemas; validating client metadata documents. |
| `uvicorn` | `cli` | Process concerns only. |
| `httpx` | `weather`, `importer`, `auth`, `server` | Network I/O is visible in exactly these places. `auth` fetches client metadata documents from trusted domains only; `server` only catches errors. |
| `playwright` | `importer` | Optional extra (`--extra browser`), imported lazily. |
| `PIL`, `pillow_heif` | `render`, `importer`, `demo` | Image work. `pillow_heif` registers once in `render`. |
| `yaml` | `catalog` | The folder format belongs to the catalog. |
| `sqlite3` | `state` | One owner of persistence. |

## Request flow: "I'm wearing the beige cords, what else?"

1. The model calls `dress_me(wearing=["beige cords"])`.
2. `server` asks `matching.resolve` to map the phrase to an `Item`. Ambiguous
   phrases come back as candidates and the model asks the user.
3. `Wardrobe.place()` picks the location: an explicit place, then the phone's
   location (<36 h old, from `state`), then `profile.yaml home`, then
   `WARDROBE_HOME`, then the last known location.
4. `weather.WeatherClient.day()` fetches Open-Meteo, falling back to MET Norway,
   and summarises the hours you're out.
5. `outfit.pick_candidates` scores items per slot (warmth vs. targets, rain,
   formality, recently worn).
6. `render.contact_sheet` draws one numbered photo grid. The tool returns text
   and that image, so the model sees the clothes.
7. The model calls `show_outfit(ids)`: `render.collage` draws the outfit image,
   `state.add_render` issues an expiring link, and the MCP Apps card
   (`ui/outfit.html`) receives structured data plus photo data URIs in `_meta`.
8. The model calls `log_wear`, and `state.log_wear` stores it with the day's
   temperatures.

## Rationale (short)

- **Folder as truth**: the user maintains the wardrobe by hand and wants no
  website. YAML + photos survive any rewrite of the server.
- **Server narrows, model chooses**: scoring is cheap and predictable; taste
  needs the photos, so the model sees a contact sheet and decides.
- **Stateless MCP over HTTP**: a home server restarts; stateless requests mean
  clients never hold dead sessions.
- **Two apps, one process**: only what ChatGPT/Claude need is public; location
  and uploads stay inside the tailnet.
- **Single-user OAuth with a passphrase**: required by the clients for a
  public endpoint, and simple enough for one person.
