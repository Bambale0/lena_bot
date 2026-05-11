#!/usr/bin/env bash
# stop.sh — остановка бота APIX (webhook-режим, без Docker)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}[apix]${NC} $*"; }
warn() { echo -e "${YELLOW}[apix]${NC} $*"; }
err()  { echo -e "${RED}[apix]${NC} $*" >&2; }
info() { echo -e "${CYAN}[apix]${NC} $*"; }

PID_FILE="$SCRIPT_DIR/.apix.pid"
LOG_FILE="$SCRIPT_DIR/apix.log"

_stop() {
  if [[ -f "$PID_FILE" ]]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
      kill "$PID" && log "Бот остановлен по PID $PID ✓"
      rm -f "$PID_FILE"
      return 0
    else
      warn "PID $PID уже не запущен"
      rm -f "$PID_FILE"
    fi
  else
    warn "PID-файл не найден. Бот через этот скрипт не запускался или уже остановлен"
  fi
}

_status() {
  echo ""
  info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  if [[ -f "$PID_FILE" ]]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
      info "  Бот: ✅ запущен (PID $PID, bg-режим)"
    else
      info "  Бот: ❌ pid-файл есть, процесс мёртв (PID $PID)"
    fi
  else
    info "  Бот: ⬜ PID-файл не найден"
  fi

  [[ -f "$LOG_FILE" ]] \
    && info "  Лог: tail -f $LOG_FILE" \
    || info "  Лог: файла нет (foreground-запуск)"

  info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
}

_logs() {
  [[ ! -f "$LOG_FILE" ]] && { warn "Лог-файл не найден (процесс запущен в fg-режиме?)"; exit 1; }
  tail -f "$LOG_FILE"
}

MODE="${1:-stop}"

case "$MODE" in
  stop|"")  _stop; _status ;;
  status)   _status ;;
  logs)     _logs ;;
  restart)
    _stop
    sleep 1
    exec "$(dirname "$0")/start.sh" bg
    ;;
  *)
    echo "Использование:"
    echo "  ./stop.sh           — остановить бота"
    echo "  ./stop.sh status    — статус процесса"
    echo "  ./stop.sh logs      — tail -f лога (bg-режим)"
    echo "  ./stop.sh restart   — перезапуск в фоне"
    exit 1
    ;;
esac
