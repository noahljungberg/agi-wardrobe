"""The architecture and documentation checkers run as part of the test suite."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_architecture_rules():
    assert _load("check_architecture").check() == []


def test_docs_are_current():
    assert _load("check_docs").check() == []
