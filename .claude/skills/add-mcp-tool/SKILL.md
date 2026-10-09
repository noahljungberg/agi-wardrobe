---
name: add-mcp-tool
description: Add or change a tool the chat model can call in the wardrobe MCP server (server.py), including its docs and tests. Use when asked for a new capability in ChatGPT/Claude ("let it pack for a trip", "add a tool that…") or to change a tool's inputs/outputs.
---

# Add or change an MCP tool

Read first: [docs/design/mcp-tools.md](../../../docs/design/mcp-tools.md) and the
"MCP tools" section of [CONVENTIONS.md](../../../CONVENTIONS.md).

## Steps

1. **Decide where the logic lives.** The tool function in `build_mcp`
   (`src/wardrobe/server.py`) only parses input, calls domain code and formats
   output. Domain logic goes in the right lower-layer module (see
   [ARCHITECTURE.md](../../../ARCHITECTURE.md)); add a module only with a layer
   entry in `scripts/check_architecture.py`.
2. **Write the tool** next to the similar existing one:
   - `@mcp.tool(title=..., annotations=read_only | writes)`. Use `read_only`
     only if nothing in the folder or state changes.
   - Parameters as `Annotated[type, Field(description=...)]`. The docstring is
     one line saying when to call it.
   - Return `str` for text-only results, or
     `CallToolResult(content=[_text(...), _image(...)])` with at most one image.
   - User mistakes come back as text or `is_error=True`, never as exceptions.
   - A UI-bound tool uses `@apps.tool(resource_uri=...)` and must be defined
     before `mcp = MCPServer(...)`.
3. **Tell the model** when to use it: add one line to `INSTRUCTIONS` if the
   trigger isn't obvious from the docstring.
4. **Test** in `tests/test_server.py` with `async with connect() as client:`
   and `FakeWeather`. Check the text the model will read and any image.
5. **Document**: add the tool's row to the table in
   `docs/design/mcp-tools.md` (`check_docs.py` fails otherwise) and update the
   README tool table.
6. Run `scripts/verify.sh`.

## Output

Report the tool name, annotations (read-only or not, and why), an example call
and reply, and the verify result.
