#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

# Register/check webhook for the isolated APIX Telegram dev bot.
# Reads .env.dev by default.

log() { printf '\n\033[1;36m[dev-webhook]\033[0m %s\n' "$*"; }
fail() { printf '\n\033[1;31m[dev-webhook:error]\033[0m %s\n' "$*" >&2; exit 1; }

command -v curl >/dev/null 2>&1 || fail "Missing command: curl"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${DEV_BOT_ENV_FILE:-$APP_DIR/.env.dev}"
DROP_PENDING="${DEV_BOT_DROP_PENDING_UPDATES:-true}"

[[ -f "$ENV_FILE" ]] || fail "Missing $ENV_FILE. Create it from .env.dev.example first."

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

: "${BOT_TOKEN:?BOT_TOKEN is required in $ENV_FILE}"
: "${WEBHOOK_URL:?WEBHOOK_URL is required in $ENV_FILE}"
: "${WEBHOOK_PATH:?WEBHOOK_PATH is required in $ENV_FILE}"
: "${WEBHOOK_SECRET:?WEBHOOK_SECRET is required in $ENV_FILE}"

if [[ "$BOT_TOKEN" == *"replace_with"* ]] || [[ "$WEBHOOK_URL" == *"example.com"* ]]; then
  fail "$ENV_FILE still contains placeholders"
fi

FULL_WEBHOOK_URL="${WEBHOOK_URL%/}${WEBHOOK_PATH}"

log "Set Telegram webhook for dev bot: $FULL_WEBHOOK_URL"
curl --fail --silent --show-error -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  --data-urlencode "url=${FULL_WEBHOOK_URL}" \
  --data-urlencode "secret_token=${WEBHOOK_SECRET}" \
  --data-urlencode "drop_pending_updates=${DROP_PENDING}"

printf '\n'
log "Current webhook info"
curl --fail --silent --show-error "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"
printf '\n'
