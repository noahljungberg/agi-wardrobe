#!/usr/bin/env bash
# The one command to run before committing. Fast (~10 s).
#   scripts/verify.sh          lint + architecture + docs + tests
#   scripts/verify.sh --quick  skip the browser and HTTP tests
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== lint";          uv run ruff check src tests scripts
echo "== architecture";  uv run python scripts/check_architecture.py
echo "== docs";          uv run python scripts/check_docs.py
echo "== tests"
if [[ "${1:-}" == "--quick" ]]; then
  uv run pytest -q --ignore=tests/test_widget.py --ignore=tests/test_http.py
else
  uv run pytest -q
fi
