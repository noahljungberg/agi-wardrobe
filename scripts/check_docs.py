#!/usr/bin/env python3
"""Catch stale or missing documentation mechanically.

Checks:
  1. every source file is listed in some docs/design/*.md
  2. every design doc is in docs/design/index.md, has a Status line and the required sections
  3. every MCP tool in server.py is documented in docs/design/mcp-tools.md
  4. every module in the architecture checker's LAYERS is named in ARCHITECTURE.md
  5. every WARDROBE_* env var read in config.py is documented
  6. relative Markdown links resolve
  7. AGENTS.md stays short

Exit code 0 = clean, 1 = problems (printed one per line).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESIGN = ROOT / "docs" / "design"
SRC = ROOT / "src" / "wardrobe"
STATUSES = ("planned", "in progress", "complete", "needs update")
REQUIRED_SECTIONS = ("## Purpose", "## Public API", "## Implementation files", "## Dependencies",
                     "## Constraints", "## Tests", "## Non-goals")
NOT_COMPONENT_DOCS = {"index.md", "overview.md"}
AGENTS_MAX_LINES = 100
SKIP_DIRS = {".venv", ".git", "node_modules", ".pytest_cache", ".ruff_cache"}


def read(path: Path, problems: list[str]) -> str:
    if not path.exists():
        problems.append(f"{path.relative_to(ROOT)} is missing")
        return ""
    return path.read_text(encoding="utf-8")


def markdown_files() -> list[Path]:
    return [p for p in ROOT.rglob("*.md") if not SKIP_DIRS & set(p.relative_to(ROOT).parts)]


def check() -> list[str]:
    problems: list[str] = []
    design_docs = sorted(DESIGN.glob("*.md"))
    design_text = {p.name: p.read_text(encoding="utf-8") for p in design_docs}
    all_design = "\n".join(design_text.values())

    # 1. source coverage
    sources = [p for p in SRC.glob("*.py") if p.name != "__init__.py"] + sorted((SRC / "ui").glob("*"))
    for path in sources:
        rel = path.relative_to(ROOT).as_posix()
        if rel not in all_design:
            problems.append(f"{rel}: not listed in any docs/design/*.md (add it to its component's 'Implementation files')")

    # 2. index, status, sections
    index = design_text.get("index.md", "")
    for name, text in design_text.items():
        if name == "index.md":
            continue
        if f"({name})" not in index:
            problems.append(f"docs/design/{name}: not linked from docs/design/index.md")
        status = re.search(r"^Status: (.+)$", text, re.M)
        if not status or not status.group(1).strip().lower().startswith(STATUSES):
            problems.append(f"docs/design/{name}: needs a line 'Status: <{' | '.join(STATUSES)}>'")
        if name not in NOT_COMPONENT_DOCS:
            for section in REQUIRED_SECTIONS:
                if not re.search(rf"^{re.escape(section)}\b", text, re.M):
                    problems.append(f"docs/design/{name}: missing section '{section}'")

    # 3. MCP tools
    server = (SRC / "server.py").read_text(encoding="utf-8")
    tools = re.findall(r"@(?:mcp|apps)\.tool\((?:[^()]|\([^()]*\))*\)\s*\n\s*async def (\w+)", server)
    tool_doc = design_text.get("mcp-tools.md", "")
    for tool in tools:
        if f"`{tool}`" not in tool_doc:
            problems.append(f"docs/design/mcp-tools.md: tool `{tool}` from server.py is not documented")
    if not tools:
        problems.append("scripts/check_docs.py: found no tools in server.py (did the decorator pattern change?)")

    # 4. architecture names every module
    arch = read(ROOT / "ARCHITECTURE.md", problems)
    layers = re.search(r"LAYERS: dict\[str, int\] = \{(.*?)\n\}", (ROOT / "scripts/check_architecture.py").read_text(), re.S)
    for module in re.findall(r'"(\w+)":', layers.group(1) if layers else ""):
        if module not in ("__init__", "__main__") and f"`{module}`" not in arch:
            problems.append(f"ARCHITECTURE.md: module `{module}` is in the layer map but not described")

    # 5. env vars
    env_vars = set(re.findall(r'"(WARDROBE_[A-Z_]+)"', (SRC / "config.py").read_text(encoding="utf-8")))
    cfg_doc = design_text.get("cli-config.md", "")
    example = read(ROOT / "deploy" / "wardrobe.env.example", problems)
    for var in sorted(env_vars):
        if var not in cfg_doc:
            problems.append(f"docs/design/cli-config.md: env var {var} is not documented")
        if var not in example:
            problems.append(f"deploy/wardrobe.env.example: env var {var} is missing")

    # 6. relative links
    for md in markdown_files():
        text = md.read_text(encoding="utf-8")
        text = re.sub(r"```.*?```", "", text, flags=re.S)  # ignore code blocks
        for target in re.findall(r"\]\(([^)\s]+)\)", text):
            if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                continue
            path = (md.parent / target.split("#")[0]).resolve()
            if not path.exists():
                problems.append(f"{md.relative_to(ROOT)}: broken link -> {target}")

    # 7. AGENTS.md length
    agents = ROOT / "AGENTS.md"
    if not agents.exists():
        problems.append("AGENTS.md is missing")
    elif len(agents.read_text(encoding="utf-8").splitlines()) > AGENTS_MAX_LINES:
        problems.append(f"AGENTS.md is longer than {AGENTS_MAX_LINES} lines; move detail into linked docs")
    return problems


def main() -> int:
    problems = check()
    for p in problems:
        print(p)
    if not problems:
        print("docs: ok")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
