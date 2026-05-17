#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

echo "== JS syntax =="
if [ -f landing/js/riot-site.js ]; then
  node --check landing/js/riot-site.js
fi

echo "== Python compile =="
if [ -d api ]; then
  python -m compileall api db main.py
fi

echo "== Health route grep =="
grep -RIn "/api/web/health\|api/web\|ws/generations" api landing main.py 2>/dev/null || true

echo "== Missing media smoke note =="
echo "Manual: curl -i https://apix.chillcreative.ru/static/upload/missing.jpg"
