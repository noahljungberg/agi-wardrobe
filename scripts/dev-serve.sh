#!/usr/bin/env bash
# Run the server locally on a demo wardrobe with auth off: MCP at http://127.0.0.1:8765/mcp
#   scripts/dev-serve.sh [wardrobe-folder]   (default: /tmp/wardrobe-demo, created if missing)
set -euo pipefail
cd "$(dirname "$0")/.."
DIR="${1:-/tmp/wardrobe-demo}"
[[ -d "$DIR/items" ]] || uv run wardrobe demo "$DIR"
export WARDROBE_DIR="$DIR" WARDROBE_AUTH=none WARDROBE_STATE_DIR="${WARDROBE_STATE_DIR:-/tmp/wardrobe-demo-state}"
export WARDROBE_HOME="${WARDROBE_HOME:-Linköping, Sweden}"
exec uv run wardrobe serve
