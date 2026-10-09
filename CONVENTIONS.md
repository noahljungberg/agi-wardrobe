# Conventions

Patterns to copy. When in doubt, imitate the nearest existing code in the same
component.

## Python

- Python 3.13. Every module starts with a docstring that says **why** it exists,
  followed by `from __future__ import annotations`.
- Type hints everywhere; `X | None`, not `Optional[X]`.
- Plain `@dataclass` for value objects (`Item`, `Place`, `DayWeather`,
  `Targets`). Use pydantic only where the MCP SDK requires it (tool parameters
  via `Annotated[..., Field(description=...)]`).
- Imports at the top of the module. The one exception is the optional
  `playwright` import in `importer.fetch_html`.
- Lint: `uv run ruff check` (rules E, F, W, I, B; long lines allowed).

## Naming

- **`colour`**, British spelling, in item.yaml, code and tool parameters. Read
  `color` only when parsing external data (JSON-LD), and convert it at once with
  `heuristics.canonical_colour`.
- Item id = the folder name, a slug from `catalog.slugify`
  (`mango-corduroy-trousers-beige`). Ids are stable: never rename a folder as a
  side effect.
- Outfit slots are exactly `outerwear, mid, base, bottoms, shoes, accessories`
  (`outfit.SLOTS`). Tops become `base` or `mid` through `layer`.
- Scales: `warmth` 0–5 and `formality` 1–5, integers.

## Errors

- **Tools don't raise for user mistakes.** Return text that says what to do
  next, or `CallToolResult(..., is_error=True)` for invalid input:

  ```python
  if item_id is not None and w.catalog.get(item_id) is None:
      return CallToolResult(content=[_text(f"No item with id {item_id!r}.")], is_error=True)
  ```

- **External services degrade instead of failing.** If weather is down, use
  `_neutral_weather`. If geocoding is down, raise `LocationUnknown`, which the
  tool turns into "ask which city". If the importer is blocked, return
  `ImportResult(error=...)`.
- A broken item.yaml must not take the server down: `Catalog` collects it in
  `catalog.errors`.
- Raise exceptions only for programmer errors (bad ids in `save_item`, config).

## Logging

- `log = logging.getLogger(__name__)` at module level. Use `log.warning(...)`
  when an external service degrades, and format exceptions with `%r`.
- Never log secrets, tokens, passphrases or full locations.
- `print` only in `cli.py` and the `scripts/`.

## MCP tools (`server.py`)

- The tool's docstring and `Field` descriptions are what the model reads.
  Write them for the model: one line, imperative, when to call.
- Set `annotations` honestly: `read_only` for anything that doesn't change the
  wardrobe or state. ChatGPT asks the user to confirm every non-read-only tool.
- Replies are read on a phone and cost context. Put text first, then at most
  one image (a contact sheet or collage); write ids in backticks; use no more
  than 40 photos per sheet.
- New tools get a row in [docs/design/mcp-tools.md](docs/design/mcp-tools.md)
  (`check_docs.py` enforces this) and a test in `tests/test_server.py`.

## HTTP

- `mcp.custom_route` routes on the public app are **unauthenticated**. Anything
  there must be protected by a random token (`/img/r/`) or an HMAC signature
  (`/img/i/`).
- Private-app handlers start with `if not authorised(request): return 401`.
- Compare secrets with `hmac.compare_digest`; generate them with `secrets.token_urlsafe`.

## Time and place

- "Today" means the user's local day: `Wardrobe.local_today(place)`, not
  `date.today()` (the server may sit in a different zone from a travelling user).
- Only the latest location is stored (`State.set_location`). Never add a
  location history.

## Heuristics (`heuristics.py`)

- `_TYPE_RULES` is first-match. Put specific patterns (`overshirt`,
  `skjortjacka`) **before** general ones (`jacket`, `skjorta`).
- Match Swedish compounds as substrings (`ullkappa` contains `kappa`); use
  `\b` only for short English words that would otherwise match inside other
  words (`\btee\b`).
- Every new rule gets a row in `tests/test_heuristics.py`.

## Tests

- One file per component: `tests/test_<component>.py`. HTTP and OAuth live in
  `tests/test_http.py`, browser rendering in `tests/test_widget.py`.
- Never touch the network. Use the `demo_dir` and `config` fixtures,
  `FakeWeather`, and `monkeypatch` for `importer.fetch_html` /
  `importer.download_images`.
- Async tests are plain `async def` (`asyncio_mode = "auto"`).
- For in-process MCP, open `async with connect() as client:` **inside** the test
  body. An async-generator fixture breaks anyio cancel scopes.

## Comments

- Explain why, not what, and only where the code would surprise a reader
  (`# rotate: the old pair stops working`).
- Don't leave commented-out code or TODOs. Put follow-ups in
  `docs/plans/known-issues.md`.

## Anti-patterns seen and rejected

- Registering `@apps.tool` after `MCPServer(...)` is constructed: the extension
  is applied at construction, so the tool silently disappears.
- Putting photos in `structuredContent`: the model reads it. Photo data URIs go
  in the result's `_meta` (`wardrobe/thumbs`).
- Returning one image per candidate: use one contact sheet.
- Treating `window.openai` as "not an MCP Apps host" in the card: ChatGPT has
  both, and only sends data after the handshake.
