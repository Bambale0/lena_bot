#!/usr/bin/env bash
# start.sh — запуск ArtFlow AI для локальной разработки и тестирования
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}[artflow]${NC} $*"; }
warn() { echo -e "${YELLOW}[artflow]${NC} $*"; }
err()  { echo -e "${RED}[artflow]${NC} $*" >&2; }
info() { echo -e "${CYAN}[artflow]${NC} $*"; }

DC="docker-compose"
docker compose version &>/dev/null 2>&1 && DC="docker compose"

if   [[ -f "venv/bin/python"  ]]; then PYTHON="venv/bin/python"
elif [[ -f ".venv/bin/python" ]]; then PYTHON=".venv/bin/python"
elif command -v python3 &>/dev/null;   then PYTHON="python3"
else err "Python не найден"; exit 1; fi

_load_env() {
  [[ ! -f ".env" ]] && { err ".env не найден! cp .env.example .env"; exit 1; }
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
}

_check_deps() {
  command -v docker &>/dev/null || { err "Docker не установлен"; exit 1; }
  [[ "${BOT_TOKEN:-}" == "" || "${BOT_TOKEN:-}" == "your_bot_token_here" ]] \
    && { err "BOT_TOKEN не задан в .env"; exit 1; }
  [[ "${COMET_API_KEY:-}" == "" || "${COMET_API_KEY:-}" == "your_cometapi_key_here" ]] \
    && warn "COMET_API_KEY не задан — генерация не будет работать"
}

_wait_for() {
  local name="$1"; shift
  local i=0
  while ! "$@" &>/dev/null; do
    i=$((i+1)); [[ $i -ge 25 ]] && { err "$name не запустился"; exit 1; }
    sleep 1
  done
  log "$name готов ✓"
}

_start_local() {
  log "Режим LOCAL — polling (webhook не нужен)"

  log "Поднимаем postgres + redis..."
  $DC up -d postgres redis

  _wait_for "PostgreSQL" $DC exec -T postgres pg_isready -U bot -d artflow
  _wait_for "Redis"      $DC exec -T redis redis-cli ping

  export DATABASE_URL="postgresql+asyncpg://bot:${DB_PASSWORD:-secret}@localhost:5433/artflow"
  export REDIS_URL="redis://localhost:6379"
  export PYTHONPATH="$SCRIPT_DIR"

  log "Применяем миграции..."
  $PYTHON -m alembic upgrade head 2>/dev/null \
    || warn "Alembic пропущен (таблицы создадутся автоматически)"

  echo ""
  info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  info "  ArtFlow AI  |  LOCAL DEV"
  info "  Python: $PYTHON"
  info "  DB:     localhost:5433/artflow"
  info "  Redis:  localhost:6379"
  info "  Стоп:   Ctrl+C  или  ./stop.sh"
  info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""

  _cleanup() {
    echo ""; log "Завершение..."
    $DC stop postgres redis 2>/dev/null || true
    exit 0
  }
  trap '_cleanup' INT TERM

  $PYTHON run_polling.py
}

_start_prod() {
  log "Режим PROD — webhook + nginx"
  $DC up -d --build
  sleep 5
  if $DC ps app 2>/dev/null | grep -qE "(Up|running)"; then
    log "Все сервисы подняты ✓"
    info "Webhook: ${WEBHOOK_URL:-}${WEBHOOK_PATH:-/webhook/telegram}"
  else
    err "app не запустился:"
    $DC logs --tail=40 app; exit 1
  fi
}

_setup_venv() {
  log "Создаём venv..."
  python3 -m venv venv
  venv/bin/pip install --upgrade pip -q
  venv/bin/pip install -r requirements.txt -q
  log "venv готов ✓ — запусти ./start.sh"
}

MODE="${1:-local}"
_load_env
_check_deps

case "$MODE" in
  local|"")  _start_local ;;
  prod)      _start_prod  ;;
  setup)     _setup_venv  ;;
  *)
    echo "Использование:"
    echo "  ./start.sh          — локальный dev (polling)"
    echo "  ./start.sh prod     — production (webhook + docker)"
    echo "  ./start.sh setup    — создать venv + deps"
    exit 1 ;;
esac
