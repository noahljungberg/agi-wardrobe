# Design index

Find the component you're changing, then read its doc **before** the code. Each
doc lists its files, public API, dependencies, constraints, tests and non-goals.
`scripts/check_docs.py` fails if a source file isn't listed in some doc here.

Status: complete

| Component | Doc | Files | Status | Trust ([QUALITY](../QUALITY.md)) |
|---|---|---|---|---|
| Product overview | [overview.md](overview.md) | (product rationale) | complete | n/a |
| Wardrobe folder | [catalog.md](catalog.md) | `catalog.py` | complete | high |
| Attribute guessing | [heuristics.md](heuristics.md) | `heuristics.py` | complete | medium |
| Fuzzy matching | [matching.md](matching.md) | `matching.py` | complete | medium |
| Runtime state | [state.md](state.md) | `state.py` | complete | high |
| Weather & places | [weather.md](weather.md) | `weather.py` | complete | medium |
| Outfit candidates | [outfit.md](outfit.md) | `outfit.py` | complete | medium |
| Images | [render.md](render.md) | `render.py` | complete | high |
| Outfit card (MCP App) | [outfit-card.md](outfit-card.md) | `ui/outfit.html` | complete (not yet seen on iPhone) | medium |
| Link importer | [importer.md](importer.md) | `importer.py` | complete (not yet run against live shops) | low |
| Wardrobe analysis | [analysis.md](analysis.md) | `analysis.py` | complete | medium |
| OAuth | [auth.md](auth.md) | `auth.py` | complete | high |
| MCP tools & `Wardrobe` service | [mcp-tools.md](mcp-tools.md) | `server.py` (tools) | complete | high |
| HTTP apps & routes | [http-api.md](http-api.md) | `server.py` (apps, routes) | complete | high |
| CLI, config, demo, deploy | [cli-config.md](cli-config.md) | `cli.py`, `config.py`, `demo.py`, `__main__.py`, `deploy/` | complete | high |

## Which doc for which task

| Task | Read |
|---|---|
| "Suggestions are too warm / ignore rain" | [outfit.md](outfit.md), then [weather.md](weather.md) |
| "It doesn't recognise what I call an item" | [matching.md](matching.md) |
| "Imported item has the wrong category/warmth" | [heuristics.md](heuristics.md) |
| "Shop X doesn't import" | [importer.md](importer.md) and the `add-shop-parser` skill |
| "Add a tool" | [mcp-tools.md](mcp-tools.md) and the `add-mcp-tool` skill |
| "The card looks wrong in ChatGPT/Claude" | [outfit-card.md](outfit-card.md) |
| "ChatGPT can't connect / login fails" | [auth.md](auth.md), [http-api.md](http-api.md), [guides/setup.md](../guides/setup.md) |
| "Location is stale" | [http-api.md](http-api.md) (`/location`), [guides/shortcuts.md](../guides/shortcuts.md) |
