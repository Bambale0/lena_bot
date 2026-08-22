#!/usr/bin/env bash
set -Eeuo pipefail

EXPECTED_SHA="${1:-}"
REPO_DIR="${DEPLOY_PATH:-/root/mkdir/lena_bot}"
APP_SUBDIR="${DEPLOY_APP_SUBDIR:-artflow}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
PUBLIC_HEALTH_URL="${DEPLOY_PUBLIC_HEALTH_URL:-https://apixbotai.com/api/v1/health}"
LOCK_FILE="${DEPLOY_LOCK_FILE:-/tmp/artflow-production-deploy.lock}"
MEDIA_CERT_DIR="${MEDIA_CERT_DIR:-/etc/letsencrypt/live/media.apixbotai.com}"

log() {
  printf '[artflow-deploy] %s\n' "$*"
}

fail() {
  printf '[artflow-deploy] ERROR: %s\n' "$*" >&2
  exit 1
}

on_error() {
  local exit_code=$?
  local line_number="${1:-unknown}"
  printf '[artflow-deploy] ERROR: deployment failed at line %s with exit code %s\n' \
    "$line_number" "$exit_code" >&2
  if [ -d "${REPO_DIR}/${APP_SUBDIR}" ]; then
    cd "${REPO_DIR}/${APP_SUBDIR}" || true
    docker compose ps >&2 || true
    docker compose logs --tail=180 app nginx postgres redis >&2 || true
  fi
  exit "$exit_code"
}

trap 'on_error "$LINENO"' ERR

command -v git >/dev/null 2>&1 || fail "git is not installed"
command -v docker >/dev/null 2>&1 || fail "docker is not installed"
command -v flock >/dev/null 2>&1 || fail "flock is not installed"
command -v curl >/dev/null 2>&1 || fail "curl is not installed"
docker compose version >/dev/null 2>&1 || fail "docker compose plugin is unavailable"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  fail "another production deployment is already running"
fi

cd "$REPO_DIR"
[ -d .git ] || fail "$REPO_DIR is not a Git repository"
[ -d "$APP_SUBDIR" ] || fail "$APP_SUBDIR is missing"
[ -f "${APP_SUBDIR}/docker-compose.yml" ] || fail "${APP_SUBDIR}/docker-compose.yml is missing"
[ -f "${APP_SUBDIR}/.env" ] || fail "${APP_SUBDIR}/.env is missing; deployment never creates production secrets"

if [ -n "$EXPECTED_SHA" ] && [[ ! "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  fail "expected commit must be a full 40-character SHA"
fi

log "fetching origin/${DEPLOY_BRANCH}"
git fetch --prune origin "$DEPLOY_BRANCH"
ORIGIN_SHA="$(git rev-parse "origin/${DEPLOY_BRANCH}")"

if [ -n "$EXPECTED_SHA" ] && [ "$ORIGIN_SHA" != "$EXPECTED_SHA" ]; then
  log "deployment skipped: tested SHA $EXPECTED_SHA was superseded by $ORIGIN_SHA"
  exit 0
fi

CURRENT_BRANCH="$(git branch --show-current)"
if [ "$CURRENT_BRANCH" != "$DEPLOY_BRANCH" ]; then
  log "switching from $CURRENT_BRANCH to $DEPLOY_BRANCH"
  git switch "$DEPLOY_BRANCH"
fi

PREVIOUS_SHA="$(git rev-parse HEAD)"
log "updating ${DEPLOY_BRANCH} with fast-forward only"
git pull --ff-only origin "$DEPLOY_BRANCH"
DEPLOYED_SHA="$(git rev-parse HEAD)"

if [ -n "$EXPECTED_SHA" ] && [ "$DEPLOYED_SHA" != "$EXPECTED_SHA" ]; then
  fail "checked out SHA $DEPLOYED_SHA does not match tested SHA $EXPECTED_SHA"
fi

cd "$APP_SUBDIR"

if [ -f nginx-media.conf ]; then
  [ -s "${MEDIA_CERT_DIR}/fullchain.pem" ] || fail \
    "media CDN certificate is missing: ${MEDIA_CERT_DIR}/fullchain.pem; issue it before deployment"
  [ -s "${MEDIA_CERT_DIR}/privkey.pem" ] || fail \
    "media CDN private key is missing: ${MEDIA_CERT_DIR}/privkey.pem; issue it before deployment"
fi

if [ -f webapp/package-lock.json ]; then
  log "building webapp assets"
  docker run --rm \
    -v "$PWD/webapp:/app" \
    -w /app \
    node:22-alpine \
    sh -lc "npm ci && npm run build"
fi

log "validating Compose configuration"
docker compose config --quiet

log "building application image"
docker compose build app

log "starting stateful dependencies"
docker compose up -d postgres redis

wait_for_container() {
  local service="$1"
  local expected_health="$2"
  local timeout_seconds="$3"
  local deadline=$((SECONDS + timeout_seconds))

  while [ "$SECONDS" -lt "$deadline" ]; do
    local container_id state health
    container_id="$(docker compose ps -q "$service")"
    if [ -n "$container_id" ]; then
      state="$(docker inspect --format '{{.State.Status}}' "$container_id")"
      health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id")"
      if [ "$state" = "running" ] && {
        [ "$expected_health" = "none" ] || [ "$health" = "$expected_health" ];
      }; then
        return 0
      fi
      if [ "$state" = "exited" ] || [ "$state" = "dead" ]; then
        docker compose logs --tail=180 "$service" >&2 || true
        fail "$service stopped before becoming ready"
      fi
    fi
    sleep 2
  done

  docker compose logs --tail=180 "$service" >&2 || true
  fail "$service did not become ready within ${timeout_seconds}s"
}

wait_for_container postgres healthy 120
wait_for_container redis healthy 120

log "applying database migrations"
# Never allow a child process to consume the deploy script's stdin. CI now
# executes this script from a remote file, and /dev/null is defense in depth for
# manual/legacy streamed execution.
docker compose run --rm -T app alembic upgrade head </dev/null

# A green deploy must mean the bot process actually runs the freshly built image.
# Force recreation avoids a stale long-lived app container surviving an otherwise
# successful git pull/build cycle.
log "starting fresh app and nginx containers"
docker compose up -d --force-recreate --remove-orphans app nginx

wait_for_container app none 120
wait_for_container nginx none 120

log "verifying Seedance 2.5 feed-repeat runtime and Telegram webhook"
docker compose exec -T app python scripts/verify_seedance25_production.py </dev/null

log "checking public health endpoint"
for attempt in $(seq 1 30); do
  if curl --fail --silent --show-error --max-time 10 "$PUBLIC_HEALTH_URL" >/dev/null; then
    log "deployment completed: $PREVIOUS_SHA -> $DEPLOYED_SHA"
    docker compose ps
    exit 0
  fi
  log "waiting for public health endpoint ($attempt/30)"
  sleep 4
done

docker compose logs --tail=180 app nginx >&2 || true
fail "public health endpoint did not become ready: $PUBLIC_HEALTH_URL"
