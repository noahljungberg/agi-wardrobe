#!/usr/bin/env python3
"""Enforce the layering and third-party boundaries described in ARCHITECTURE.md.

Exit code 0 = clean, 1 = violations (printed one per line).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "src" / "wardrobe"

# Keep in sync with ARCHITECTURE.md. A module may import only from strictly lower layers.
LAYERS: dict[str, int] = {
    "__init__": 0, "config": 0, "heuristics": 0, "state": 0, "weather": 0,
    "catalog": 1,
    "matching": 2, "outfit": 2, "render": 2,
    "analysis": 3, "importer": 3, "auth": 3, "demo": 3,
    "server": 4,
    "cli": 5,
    "__main__": 6,
}

# Third-party packages and the only modules allowed to import them.
THIRD_PARTY: dict[str, set[str]] = {
    "mcp": {"server", "auth"},
    "mcp_types": {"server"},
    "starlette": {"server", "auth"},
    "uvicorn": {"cli"},
    "pydantic": {"server", "auth"},
    "httpx": {"weather", "importer", "auth", "server"},
    "playwright": {"importer"},
    "PIL": {"render", "importer", "demo"},
    "pillow_heif": {"render"},
    "yaml": {"catalog"},
    "sqlite3": {"state"},
}


def imports_of(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if node.module == "wardrobe":  # `from wardrobe import importer`
                found += [(node.lineno, f"wardrobe.{alias.name}") for alias in node.names]
            else:
                found.append((node.lineno, node.module))
    return found


def check() -> list[str]:
    problems: list[str] = []
    for path in sorted(PKG.glob("*.py")):
        module = path.stem
        rel = path.relative_to(ROOT)
        if module not in LAYERS:
            problems.append(f"{rel}: module has no layer in scripts/check_architecture.py LAYERS (and ARCHITECTURE.md)")
            continue
        for lineno, name in imports_of(path):
            top = name.split(".")[0]
            if top == "wardrobe":
                target = name.split(".")[1] if "." in name else "__init__"
                if target not in LAYERS:
                    problems.append(f"{rel}:{lineno}: imports unknown module wardrobe.{target}")
                elif LAYERS[target] >= LAYERS[module]:
                    problems.append(
                        f"{rel}:{lineno}: {module} (layer {LAYERS[module]}) must not import {target} (layer {LAYERS[target]})"
                    )
            elif top in THIRD_PARTY and module not in THIRD_PARTY[top]:
                allowed = ", ".join(sorted(THIRD_PARTY[top]))
                problems.append(f"{rel}:{lineno}: {top} may only be imported by: {allowed}")
    return problems


def main() -> int:
    problems = check()
    for p in problems:
        print(p)
    if not problems:
        print("architecture: ok")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
