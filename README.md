# Wardrobe

A personal stylist that lives inside ChatGPT or Claude on your phone. You say:

> "I've got the beige Mango cords on today"

It checks the weather where you are, looks at photos of your actual clothes,
and shows you an outfit as a card of photos with a short note. It also logs
what you wore, so it doesn't suggest the same shirt two days running, and it
can tell you what's missing from your wardrobe.

No website and no app to open: it's an MCP server on your home machine,
reached through Tailscale Funnel.

```
 iPhone: ChatGPT / Claude ──► https://<machine>.<tailnet>.ts.net/mcp   (Funnel, OAuth login)
 iPhone Shortcuts ─────────► https://<machine>.<tailnet>.ts.net:8443  (tailnet only)
                                          │
                         home machine: `wardrobe serve`
                         ├─ your folder: items/<id>/item.yaml + photos
                         ├─ weather: Open-Meteo (MET Norway fallback)
                         └─ state: wear log, preferences, last location
```

## Try it in two minutes

```sh
uv sync
uv run wardrobe demo /tmp/wardrobe-demo
WARDROBE_DIR=/tmp/wardrobe-demo WARDROBE_AUTH=none WARDROBE_HOME="Linköping, Sweden" uv run wardrobe serve
# MCP endpoint: http://127.0.0.1:8765/mcp (e.g. with the MCP Inspector)
```

For the real setup (Arch, systemd, Tailscale Funnel, ChatGPT, iPhone
Shortcuts), see **[docs/guides/setup.md](docs/guides/setup.md)**.

## What the assistant can do

| Tool | What it's for |
|---|---|
| `dress_me` | Weather where you are, plus candidates per slot as a numbered photo sheet the model can see |
| `show_outfit` | The outfit as an inline photo card (MCP Apps / ChatGPT), a collage image and a link |
| `log_wear` | "I'm wearing…" / "wore … yesterday" |
| `find_items` | "Do I have a navy knit?", with photos |
| `save_item` | Add or edit items, attach inbox photos, retire things |
| `review_inbox` | Photos you sent from the phone, waiting to be described |
| `import_links` | Product links → photos + prefilled details |
| `wardrobe_analysis` | Gaps, near-duplicates, hard-to-combine items, cost per wear, never worn |
| `remember` / `forget` | Lasting preferences ("never black with brown") |
| `set_location` | "I'm in San Francisco" |

## Commands

```sh
uv run wardrobe serve                 # MCP (public port) + Shortcuts API (private port)
uv run wardrobe import --file links.txt
uv run wardrobe check                 # validate the folder
uv run wardrobe demo <folder>         # demo wardrobe with drawn photos
uv run wardrobe secret                # random passphrase/token
uv run pytest -q
scripts/verify.sh                     # lint + architecture + docs checks + tests
```

## Docs

For people:

- [docs/guides/setup.md](docs/guides/setup.md): install, Tailscale, connecting ChatGPT/Claude
- [docs/guides/wardrobe-folder.md](docs/guides/wardrobe-folder.md): folder and `item.yaml` format
- [docs/guides/shortcuts.md](docs/guides/shortcuts.md): the three iPhone Shortcuts

For coding agents (and anyone changing the code): start at [AGENTS.md](AGENTS.md). It routes to
[ARCHITECTURE.md](ARCHITECTURE.md), [CONVENTIONS.md](CONVENTIONS.md), the
[design index](docs/design/index.md), the [plans](docs/plans/) and the
[quality ledger](docs/QUALITY.md).
