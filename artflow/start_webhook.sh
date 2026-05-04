#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -f "$SCRIPT_DIR/venv/bin/uvicorn" ]]; then
  UVICORN="$SCRIPT_DIR/venv/bin/uvicorn"
elif [[ -f "$SCRIPT_DIR/.venv/bin/uvicorn" ]]; then
  UVICORN="$SCRIPT_DIR/.venv/bin/uvicorn"
else
  echo "uvicorn not found in venv/.venv" >&2
  exit 1
fi

if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
  echo ".env not found" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source "$SCRIPT_DIR/.env"
set +a

export PYTHONPATH="$SCRIPT_DIR"

exec "$UVICORN" main:app --host 127.0.0.1 --port "${API_PORT:-7777}" --workers 1
