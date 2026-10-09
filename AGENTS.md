# AGENTS.md: Wardrobe

## Purpose

An MCP server that runs on the owner's home machine (Arch Linux, behind Tailscale
Funnel) and gives ChatGPT/Claude on an iPhone access to their real wardrobe:
item photos, where they are, the weather there, outfit suggestions shown as a
photo card, a wear log and gap analysis. The product rationale is in
[docs/design/overview.md](docs/design/overview.md).

## Where things are

| Need | Read |
|---|---|
| Layers, boundaries, dependency rules | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Code patterns to copy | [CONVENTIONS.md](CONVENTIONS.md) |
| Which component owns what (start here for any code change) | [docs/design/index.md](docs/design/index.md) |
| Current work | [docs/plans/active/](docs/plans/active/) |
| What's trustworthy, what isn't | [docs/QUALITY.md](docs/QUALITY.md) |
| Non-blocking debt | [docs/plans/known-issues.md](docs/plans/known-issues.md) |
| User-facing setup/format docs | [docs/guides/](docs/guides/) |
| Repeatable workflows (skills) | [.claude/skills/](.claude/skills/) |

## Task protocol

1. Read this file, then the user request and any active plan it touches.
2. Find the component in [docs/design/index.md](docs/design/index.md) and read
   its design doc **before** opening code. It lists its files, API, rules and tests.
3. Read the code and tests of that component only.
4. Make the smallest change that satisfies the task. Follow the conventions.
5. Run `scripts/verify.sh` (or `scripts/verify.sh --quick` while iterating).
6. If you changed durable knowledge (API, files, rules, status, trust), update
   the component doc, `docs/QUALITY.md`, or `known-issues.md` in the same change.
7. Stop when the requested task is done. Log follow-ups in `known-issues.md`
   instead of doing them.

Session recovery: `git log --oneline -10`, then the active plan's progress log,
then `scripts/verify.sh`.

## Commands

```sh
uv sync --extra browser      # install (browser extra = Playwright for the importer)
scripts/verify.sh            # lint + architecture + docs checks + all tests (~10 s)
scripts/verify.sh --quick    # same without browser/HTTP tests
scripts/dev-serve.sh         # local server on a demo wardrobe, auth off, MCP at :8765/mcp
uv run wardrobe check        # validate a wardrobe folder (needs WARDROBE_DIR)
```

## Hard rules

- `scripts/check_architecture.py` enforces layers and which module may import
  `mcp`, `starlette`, `httpx`, `PIL`, `yaml`, `sqlite3`. Don't weaken it to make
  a change pass; move the code instead.
- `scripts/check_docs.py` fails when a source file, MCP tool, env var or design
  doc isn't documented. Fix the doc, not the checker.
- The wardrobe folder is the user's data and stays hand-editable: only
  `catalog.py` writes it, and only through `Catalog.save_item`.
- Never put personal data (addresses, order numbers, emails, real wardrobe
  contents) in the repo. Tests use `wardrobe.demo` and fakes.
- No network in tests: use `FakeWeather` and monkeypatched importer fetches
  (see `tests/conftest.py`).
- Tool replies are read on a phone: keep model-facing text compact.
