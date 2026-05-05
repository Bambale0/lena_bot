#!/usr/bin/env bash
# start.sh — локальный запуск бота APIX в webhook-режиме без Docker
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
UVICORN_HOST="${UVICORN_HOST:-127.0.0.1}"
UVICORN_PORT="${API_PORT:-7777}"

# ── Python ────────────────────────────────────────────────────────────────────
if   [[ -f "$SCRIPT_DIR/venv/bin/python"  ]]; then PYTHON="$SCRIPT_DIR/venv/bin/python"
elif [[ -f "$SCRIPT_DIR/.venv/bin/python" ]]; then PYTHON="$SCRIPT_DIR/.venv/bin/python"
elif command -v python3 &>/dev/null;              then PYTHON="$(command -v python3)"
else err "Python 3 не найден"; exit 1; fi

if   [[ -f "$SCRIPT_DIR/venv/bin/uvicorn"  ]]; then UVICORN="$SCRIPT_DIR/venv/bin/uvicorn"
elif [[ -f "$SCRIPT_DIR/.venv/bin/uvicorn" ]]; then UVICORN="$SCRIPT_DIR/.venv/bin/uvicorn"
else err "uvicorn не найден в venv/.venv"; exit 1; fi

# ── .env ──────────────────────────────────────────────────────────────────────
_load_env() {
  [[ ! -f "$SCRIPT_DIR/.env" ]] && {
    err ".env не найден!  →  cp .env.example .env  и заполни токены"
    exit 1
  }
  set -a
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/.env"
  set +a
}

# ── Проверки ──────────────────────────────────────────────────────────────────
_check() {
  [[ "${BOT_TOKEN:-}" == "" || "${BOT_TOKEN:-}" == "your_bot_token_here" ]] && {
    err "BOT_TOKEN не задан в .env"; exit 1; }
  [[ "${WEBHOOK_URL:-}" == "" ]] && {
    err "WEBHOOK_URL не задан в .env"; exit 1; }
  [[ "${WEBHOOK_SECRET:-}" == "" || "${WEBHOOK_SECRET:-}" == "change_me_secret" ]] && {
    warn "WEBHOOK_SECRET не задан или оставлен дефолтным"; }
  [[ "${COMET_API_KEY:-}" == "" || "${COMET_API_KEY:-}" == "your_cometapi_key_here" ]] && {
    warn "COMET_API_KEY не задан — часть генераций работать не будет"; }
}

# ── Проверка сервисов (postgres / redis) ──────────────────────────────────────
_check_postgres() {
  if command -v pg_isready &>/dev/null; then
    pg_isready -h "${PG_HOST:-localhost}" -p "${PG_PORT:-5432}" -U "${PG_USER:-bot}" &>/dev/null \
      && { log "PostgreSQL доступен ✓"; return 0; }
    err "PostgreSQL недоступен на ${PG_HOST:-localhost}:${PG_PORT:-5432}"
    echo "  Запусти postgres или укажи DATABASE_URL в .env"
    exit 1
  else
    warn "pg_isready не найден — проверка postgres пропущена"
  fi
}

_check_redis() {
  if command -v redis-cli &>/dev/null; then
    redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" ping &>/dev/null \
      && { log "Redis доступен ✓"; return 0; }
    err "Redis недоступен на ${REDIS_HOST:-localhost}:${REDIS_PORT:-6379}"
    echo "  Запусти redis-server или укажи REDIS_URL в .env"
    exit 1
  else
    warn "redis-cli не найден — проверка redis пропущена"
  fi
}

# ── venv + зависимости ────────────────────────────────────────────────────────
_setup() {
  log "Создаём виртуальное окружение..."
  python3 -m venv venv
  log "Устанавливаем зависимости..."
  venv/bin/pip install --upgrade pip -q
  venv/bin/pip install -r requirements.txt -q
  PYTHON="$SCRIPT_DIR/venv/bin/python"
  log "venv готов ✓"
}

# ── Миграции ─────────────────────────────────────────────────────────────────
_migrate() {
  log "Применяем миграции Alembic..."
  PYTHONPATH="$SCRIPT_DIR" $PYTHON -m alembic upgrade head
  log "Миграции применены ✓"
}

# ── Запуск бота в webhook-режиме (foreground) ────────────────────────────────
_start_fg() {
  log "Запуск бота в webhook-режиме (foreground, Ctrl+C для остановки)..."
  echo ""
  info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  info "  APIX  |  BOT WEBHOOK MODE"
  info "  Python:   $PYTHON"
  info "  Uvicorn:  $UVICORN"
  info "  DB:       ${DATABASE_URL:-не задан}"
  info "  Redis:    ${REDIS_URL:-redis://localhost:6379}"
  info "  Webhook:  ${WEBHOOK_URL:-не задан}${WEBHOOK_PATH:-/webhook/telegram}"
  info "  Listen:   http://${UVICORN_HOST}:${UVICORN_PORT}"
  info "  Лог:      (консоль)"
  info "  Стоп:     Ctrl+C"
  info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""

  export PYTHONPATH="$SCRIPT_DIR"
  exec "$UVICORN" main:app --host "$UVICORN_HOST" --port "$UVICORN_PORT" --workers 1
}

# ── Запуск бота в webhook-режиме (background, записывает PID) ────────────────
_start_bg() {
  if [[ -f "$PID_FILE" ]]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
      warn "Бот уже запущен (PID $OLD_PID). Остановка: ./stop.sh"
      exit 1
    else
      rm -f "$PID_FILE"
    fi
  fi

  log "Запуск бота в webhook-режиме (background)..."
  export PYTHONPATH="$SCRIPT_DIR"
  nohup "$UVICORN" main:app --host "$UVICORN_HOST" --port "$UVICORN_PORT" --workers 1 >> "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  sleep 2

  if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    log "Бот запущен ✓ (PID $(cat "$PID_FILE"))"
    info "Лог:   tail -f $LOG_FILE"
    info "Стоп:  ./stop.sh"
  else
    err "Бот упал сразу после запуска. Лог:"
    tail -20 "$LOG_FILE"
    exit 1
  fi
}

# ── Entry point ───────────────────────────────────────────────────────────────
MODE="${1:-fg}"

_load_env
_check

case "$MODE" in
  fg|run)
    _check_postgres
    _check_redis
    _migrate
    _start_fg
    ;;
  bg|daemon)
    _check_postgres
    _check_redis
    _migrate
    _start_bg
    ;;
  setup)
    _setup
    ;;
  migrate)
    _migrate
    ;;
  *)
    echo ""
    echo "Использование:"
    echo "  ./start.sh           — запуск бота в webhook-режиме (foreground)"
    echo "  ./start.sh fg        — то же самое"
    echo "  ./start.sh bg        — запуск бота в webhook-режиме (background)"
    echo "  ./start.sh setup     — создать venv + установить зависимости"
    echo "  ./start.sh migrate   — только применить миграции"
    echo ""
    exit 1
    ;;
esac
