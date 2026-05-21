#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -f "$SCRIPT_DIR/venv/bin/uvicorn" ]]; then
  PYTHON_BIN="$SCRIPT_DIR/venv/bin/python"
elif [[ -f "$SCRIPT_DIR/.venv/bin/uvicorn" ]]; then
  PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
else
  echo "uvicorn not found in venv/.venv" >&2
  exit 1
fi

"$PYTHON_BIN" - <<'PY'
import sys
required = (3, 12)
current = sys.version_info[:2]
if current < required:
    raise SystemExit(f"Python {required[0]}.{required[1]}+ required, got {current[0]}.{current[1]}")
PY

if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
  echo ".env not found" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source "$SCRIPT_DIR/.env"
set +a

export PYTHONPATH="$SCRIPT_DIR"

"$PYTHON_BIN" -m alembic upgrade head

exec "$PYTHON_BIN" -m uvicorn main:app --host 127.0.0.1 --port "${API_PORT:-7777}" --workers 1
