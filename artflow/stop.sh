#!/usr/bin/env bash
# stop.sh — остановка ArtFlow AI
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}[artflow]${NC} $*"; }
warn() { echo -e "${YELLOW}[artflow]${NC} $*"; }
info() { echo -e "${CYAN}[artflow]${NC} $*"; }

DC="docker-compose"
docker compose version &>/dev/null 2>&1 && DC="docker compose"

MODE="${1:-local}"

_stop_local() {
  log "Останавливаем local-сервисы (postgres + redis)..."

  # Убиваем polling-процессы если есть
  if pgrep -f "run_polling.py" &>/dev/null; then
    pkill -f "run_polling.py" && log "Polling процесс остановлен ✓" || true
  fi

  $DC stop postgres redis 2>/dev/null && log "postgres + redis остановлены ✓" || warn "Сервисы уже остановлены"
  echo ""
  info "Данные сохранены в Docker volumes (pgdata, redisdata)"
  info "Для полного удаления данных: ./stop.sh purge"
}

_stop_prod() {
  log "Останавливаем все prod-сервисы..."
  $DC down && log "Все сервисы остановлены ✓"
}

_stop_purge() {
  warn "ВНИМАНИЕ: удаляем ВСЕ контейнеры И данные (volumes)!"
  read -r -p "Продолжить? [y/N] " confirm
  [[ "${confirm,,}" != "y" ]] && { log "Отменено"; exit 0; }

  # Убиваем polling если запущен
  pkill -f "run_polling.py" 2>/dev/null || true

  $DC down -v --remove-orphans 2>/dev/null || true
  log "Все контейнеры и volumes удалены ✓"
}

_show_status() {
  echo ""
  info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  info "  Статус контейнеров:"
  $DC ps 2>/dev/null || echo "  (нет запущенных контейнеров)"
  info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
}

case "$MODE" in
  local|"")  _stop_local; _show_status ;;
  prod)      _stop_prod;  _show_status ;;
  purge)     _stop_purge; _show_status ;;
  status)    _show_status ;;
  *)
    echo "Использование:"
    echo "  ./stop.sh           — остановить local-сервисы"
    echo "  ./stop.sh prod      — остановить все prod-сервисы"
    echo "  ./stop.sh purge     — удалить всё включая данные БД"
    echo "  ./stop.sh status    — показать статус контейнеров"
    exit 1 ;;
esac
