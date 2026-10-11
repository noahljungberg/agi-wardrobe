# CLI, configuration, demo and deployment

Status: complete

## Purpose

Process-level concerns: reading configuration from the environment, the
`wardrobe` command, the demo wardrobe generator, and the files that run it on
the home machine.

## Public API

Commands (`wardrobe = wardrobe.cli:main`, also `python -m wardrobe`):

| Command | Does |
|---|---|
| `wardrobe serve` | Both uvicorn servers in one asyncio loop; SIGTERM stops both |
| `wardrobe import <url>… / --file links.txt` | Imports links into `WARDROBE_DIR`; exit 1 if any fail |
| `wardrobe check` | Lists items, missing photos, guessed fields, inbox; exit 1 on broken files |
| `wardrobe demo <folder>` | 16 demo items with drawn photos + `profile.yaml` (no config needed) |
| `wardrobe tryon <item>… [--styling …]` | Draws the outfit on you with the signed-in Codex CLI (what `try_on` does) and prints the picture's path; exit 1 on failure |
| `wardrobe secret` | Prints a random token |

Environment (`Config.from_env`):

| Variable | Default | Meaning |
|---|---|---|
| `WARDROBE_DIR` | (required) | The wardrobe folder |
| `WARDROBE_STATE_DIR` | `~/.local/state/wardrobe` | SQLite + cache |
| `WARDROBE_PUBLIC_URL` | `http://127.0.0.1:<public port>` | Funnel URL; OAuth issuer and image links |
| `WARDROBE_AUTH` | `oauth` | `oauth` or `none` (local testing only) |
| `WARDROBE_PASSPHRASE` | (required with oauth, ≥8 chars) | Login passphrase |
| `WARDROBE_DEVICE_TOKEN` | unset (private API open inside the tailnet) | Bearer token for Shortcuts |
| `WARDROBE_BIND` | `127.0.0.1` | Bind address for both apps |
| `WARDROBE_PUBLIC_PORT` | `8765` | Public app |
| `WARDROBE_PRIVATE_PORT` | `8766` | Private app |
| `WARDROBE_HOME` | unset | Fallback location (after `profile.yaml home`) |
| `WARDROBE_CHROMIUM` | unset (Playwright's browser) | Chromium binary for the importer, e.g. `/usr/bin/chromium` |
| `WARDROBE_CODEX` | `codex` | Codex CLI for outfit pictures ([tryon.md](tryon.md)): a command on PATH or a full path; `off` disables them |
| `WARDROBE_CODEX_MODEL` | unset (Codex's default) | Agent model for those runs, only if Codex rejects its default for ChatGPT sign-in |

## Implementation files

- `src/wardrobe/cli.py`: argument parsing, `serve`, `check`, `try_on`, `import_links`.
- `src/wardrobe/config.py`: `Config`, `ConfigError`.
- `src/wardrobe/demo.py`: `make_demo(root)`, `DEMO_ITEMS`. Also the test
  fixture data.
- `src/wardrobe/__main__.py`
- `deploy/wardrobe.service`: systemd **user** unit; `deploy/wardrobe.env.example`.
- The setup guide for people: [guides/setup.md](../guides/setup.md).

## Dependencies

- `cli` may import anything; `uvicorn` only here.
- `config` imports nothing internal. `demo` uses `catalog` and `PIL`.

## Constraints

- A new env var needs a row in this table **and** a line in
  `deploy/wardrobe.env.example` (`check_docs.py` enforces both).
- `demo.py` data must stay generic: no real personal wardrobe or order data.
- The systemd unit assumes the checkout at `~/agi-wardrobe` and env at
  `~/.config/wardrobe/wardrobe.env`.

## Tests

- `tests/conftest.py` builds `Config.from_env({...})` and a demo wardrobe for
  every test.
- The CLI `serve` start/stop was verified manually (see the build log in
  [plans/completed/2026-10-09-v0.1-build.md](../plans/completed/2026-10-09-v0.1-build.md)).
  There's no automated CLI test yet (known issue).

## Non-goals

- No Docker image (Arch + uv + systemd is the target). No config file format
  besides env.
