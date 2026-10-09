# Quality ledger

How much to trust each component, and why. Update a row when tests, real-world
verification or known risks change.

Trust levels:

- **high**: covered by tests at its boundary and exercised end to end.
- **medium**: tested, but the behaviour is heuristic or depends on outside
  systems seen only in fixtures.
- **low**: implemented, but the main path hasn't run against the real outside
  world yet.

Last reviewed: 2026-10-09 (v0.1)

| Component | Trust | Evidence | Main risk |
|---|---|---|---|
| [catalog](design/catalog.md) | high | `test_catalog.py`; used by every tool test | Very large folders (>2000 items) scan slowly |
| [heuristics](design/heuristics.md) | medium | 14 real product names (Mango, Zalando, Levi's) plus materials and colours in `test_heuristics.py` | Unseen naming patterns get the wrong category. The model can fix them via `save_item` |
| [matching](design/matching.md) | medium | `test_matching.py` with real phrasing | Very similar items are reported as ambiguous (by design); aliases fix this |
| [state](design/state.md) | high | `test_state.py`, OAuth via `test_http.py` | No schema migrations yet |
| [weather](design/weather.md) | medium | Fixture tests for both providers; live Open-Meteo and MET Norway calls checked manually | Open-Meteo 429s on shared IPs (fallback covers it); approximate time zone if unknown |
| [outfit](design/outfit.md) | medium | `test_outfit.py` | Thresholds are hand-tuned and need real-use feedback |
| [render](design/render.md) | high | `test_render.py`; collage and contact sheet visually checked | HEIC test skips when the wheel lacks an encoder |
| [outfit card](design/outfit-card.md) | medium | `test_widget.py` in Chromium, both host protocols plus the ChatGPT hybrid, light and dark | Empty frame seen in ChatGPT web on 2026-10-09 (handshake skipped); fixed, **awaiting confirmation in ChatGPT/Claude** |
| [importer](design/importer.md) | low | `test_importer.py` on Mango-/Zalando-shaped fixtures | **Live shop pages block datacenter IPs; never run from the home connection yet** |
| [analysis](design/analysis.md) | medium | `test_analysis.py` | Compatibility rule is coarse (neutral/same colour) |
| [auth](design/auth.md) | high | Full OAuth flow over real HTTP in `test_http.py`, both DCR and CIMD (Claude's default) | Real ChatGPT/Claude clients not yet connected |
| [mcp tools](design/mcp-tools.md) | high | `test_server.py` in-process + over HTTP | Model behaviour with these tools is untested on real chats |
| [http api](design/http-api.md) | high | `test_http.py` | Tailscale Funnel's Host-header behaviour assumed, not observed |
| [cli/config/deploy](design/cli-config.md) | high | Config tested through fixtures; `serve` start/SIGTERM checked by hand | systemd unit not yet run on the Arch machine |

## Verification commands

```sh
scripts/verify.sh           # everything: lint, architecture, docs, 68 tests (~10 s)
scripts/verify.sh --quick   # without browser/HTTP tests
```

## What would raise trust next

See [plans/active/first-deployment.md](plans/active/first-deployment.md). Seeing
the card on the iPhone, running the importer from home and one week of real
use would move the outfit card, importer and outfit rows up.
