#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

# Deploy an isolated APIX Telegram dev bot instance.
#
# Usage from artflow/:
#   bash scripts/deploy-dev-bot.sh [branch]
#
# Required first-time file:
#   cp .env.dev.example .env.dev
#   nano .env.dev
#
# Useful env:
#   DEV_BOT_ENV_FILE=.env.dev
#   DEV_BOT_COMPOSE_FILE=docker-compose.dev-bot.yml
#   DEV_BOT_PROJECT=artflow_devbot
#   DEV_BOT_NETWORK=apix_devbot_backend
#   DEV_BOT_APP_PORT=8010
#   DEV_BOT_BRANCH=agent/miniapp-shadcn-rework
#   DEV_BOT_NODE_MODE=auto        # auto|local|docker
#   DEV_BOT_NO_CACHE=1            # force Docker app rebuild without cache

log() { printf '\n\033[1;36m[dev-bot]\033[0m %s\n' "$*"; }
fail() { printf '\n\033[1;31m[dev-bot:error]\033[0m %s\n' "$*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing command: $1"
}

require_cmd git
require_cmd docker

docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 plugin is required"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
REPO_DIR="$(git -C "$APP_DIR" rev-parse --show-toplevel)"
WEBAPP_DIR="$APP_DIR/webapp"
ENV_FILE="${DEV_BOT_ENV_FILE:-$APP_DIR/.env.dev}"
COMPOSE_FILE="${DEV_BOT_COMPOSE_FILE:-$APP_DIR/docker-compose.dev-bot.yml}"
PROJECT="${DEV_BOT_PROJECT:-artflow_devbot}"
NETWORK="${DEV_BOT_NETWORK:-apix_devbot_backend}"
NODE_MODE="${DEV_BOT_NODE_MODE:-auto}"
TARGET_BRANCH="${1:-${DEV_BOT_BRANCH:-$(git -C "$REPO_DIR" branch --show-current)}}"

[[ -f "$ENV_FILE" ]] || fail "Create dev env first: cp .env.dev.example .env.dev && nano .env.dev"
[[ -f "$COMPOSE_FILE" ]] || fail "Missing compose file: $COMPOSE_FILE"
[[ -f "$WEBAPP_DIR/package-lock.json" ]] || fail "Missing webapp/package-lock.json"

if grep -q 'replace_with_dev_bot_token\|dev-apix.example.com\|replace_with_random_dev_webhook_secret' "$ENV_FILE"; then
  fail "$ENV_FILE still contains placeholders. Fill BOT_TOKEN, WEBHOOK_URL, WEBHOOK_SECRET and BOT_USERNAME."
fi

log "Fetch branch: $TARGET_BRANCH"
git -C "$REPO_DIR" fetch --prune origin "$TARGET_BRANCH"

if git -C "$REPO_DIR" show-ref --verify --quiet "refs/heads/$TARGET_BRANCH"; then
  git -C "$REPO_DIR" switch "$TARGET_BRANCH"
else
  git -C "$REPO_DIR" switch -c "$TARGET_BRANCH" --track "origin/$TARGET_BRANCH"
fi

git -C "$REPO_DIR" reset --hard "origin/$TARGET_BRANCH"

build_webapp_local() {
  require_cmd npm
  (cd "$WEBAPP_DIR" && rm -rf dist node_modules && npm ci && npm run build)
}

build_webapp_docker() {
  docker run --rm -v "$WEBAPP_DIR:/app" -w /app node:22-alpine sh -lc 'rm -rf dist node_modules && npm ci && npm run build'
}

log "Build webapp ($NODE_MODE)"
case "$NODE_MODE" in
  local) build_webapp_local ;;
  docker) build_webapp_docker ;;
  auto)
    if command -v npm >/dev/null 2>&1; then
      build_webapp_local || build_webapp_docker
    else
      build_webapp_docker
    fi
    ;;
  *) fail "Unknown DEV_BOT_NODE_MODE=$NODE_MODE" ;;
esac

[[ -f "$WEBAPP_DIR/dist/index.html" ]] || fail "webapp/dist/index.html was not created"

export DEV_BOT_APP_PORT="${DEV_BOT_APP_PORT:-8010}"
export DEV_BOT_POSTGRES_PORT="${DEV_BOT_POSTGRES_PORT:-5434}"
export DEV_BOT_REDIS_PORT="${DEV_BOT_REDIS_PORT:-6380}"
export DEV_BOT_NETWORK="$NETWORK"

log "Ensure shared Docker network: $NETWORK"
docker network inspect "$NETWORK" >/dev/null 2>&1 || docker network create "$NETWORK" >/dev/null

log "Validate dev compose"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -p "$PROJECT" config --quiet

log "Deploy isolated dev bot project=$PROJECT port=127.0.0.1:$DEV_BOT_APP_PORT"
if [[ "${DEV_BOT_NO_CACHE:-0}" == "1" ]]; then
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -p "$PROJECT" build --no-cache app
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -p "$PROJECT" up -d --remove-orphans
else
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -p "$PROJECT" up -d --build --remove-orphans
fi

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -p "$PROJECT" ps

log "Smoke check"
if command -v curl >/dev/null 2>&1; then
  curl --fail --silent --show-error --max-time 10 "http://127.0.0.1:${DEV_BOT_APP_PORT}/app" >/dev/null \
    && log "Mini App responds on http://127.0.0.1:${DEV_BOT_APP_PORT}/app" \
    || log "Mini App smoke check failed; inspect: docker compose --env-file $ENV_FILE -f $COMPOSE_FILE -p $PROJECT logs --tail=120 app"
fi

log "Done. Public dev URL must proxy to 127.0.0.1:${DEV_BOT_APP_PORT}. Then run: bash scripts/set-dev-bot-webhook.sh"