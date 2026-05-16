#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
ARTFLOW="$ROOT/artflow"
if [ -d "$ARTFLOW" ]; then
  cd "$ARTFLOW"
fi

echo "== compileall =="
python -m compileall core api db bot main.py

echo "== import app =="
python - <<'PY'
import main
print("FastAPI app import: OK", getattr(main.app, "title", ""))
PY

echo "== pytest =="
if command -v pytest >/dev/null 2>&1; then
  pytest -q
else
  python -m pytest -q
fi
