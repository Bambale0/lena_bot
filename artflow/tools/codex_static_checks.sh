#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
ARTFLOW="$ROOT/artflow"
if [ -d "$ARTFLOW" ]; then
  cd "$ARTFLOW"
fi

if [ -n "${PYTHON_BIN:-}" ]; then
  PYTHON="$PYTHON_BIN"
elif [ -x "venv/bin/python" ]; then
  PYTHON="venv/bin/python"
elif [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
elif command -v python3.12 >/dev/null 2>&1; then
  PYTHON="$(command -v python3.12)"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  PYTHON="python"
fi

echo "== python =="
"$PYTHON" - <<'PY'
import sys
print(sys.executable)
print(sys.version.split()[0])
PY

echo "== compileall =="
"$PYTHON" -m compileall core api db bot main.py

echo "== import app =="
"$PYTHON" - <<'PY'
import main
print("FastAPI app import: OK", getattr(main.app, "title", ""))
PY

echo "== pytest =="
if ! "$PYTHON" - <<'PY'
import importlib.util
raise SystemExit(0 if importlib.util.find_spec("pytest") else 1)
PY
then
  echo "pytest is not installed for $PYTHON; run: $PYTHON -m pip install -r requirements-dev.txt" >&2
  exit 1
fi
"$PYTHON" -m pytest -q
