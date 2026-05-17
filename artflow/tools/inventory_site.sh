#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

OUT=".codex_inventory"
mkdir -p "$OUT"

{
  echo "# Routes inventory"
  grep -RIn "@app\.\\|@router\.\\|include_router\\|/api/web\\|/api/v1" main.py api landing/js 2>/dev/null || true
} > "$OUT/routes.txt"

{
  echo "# Landing screens hints"
  grep -RIn "home\\|studio\\|prompts\\|feed\\|works\\|billing\\|profile\\|render" landing/js/riot-site.js 2>/dev/null || true
} > "$OUT/landing_screens.txt"

{
  echo "# CSS components hints"
  grep -RIn "drawer\\|toast\\|card\\|prompt\\|feed\\|studio\\|queue" landing/css/riot-site.css 2>/dev/null || true
} > "$OUT/css_components.txt"

echo "Inventory written to $OUT"
