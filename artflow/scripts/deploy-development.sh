#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

# Development auto-deploy helper for the Artflow Mini App stack.
#
# Purpose:
# - make a dev server match the selected Git branch;
# - rebuild the React Mini App assets from a clean webapp workspace;
# - rebuild/recreate Docker Compose services;
# - avoid the stale host/container dist mismatch that is easy to hit during UI work.
#
# Usage from anywhere inside the repository:
#   bash artflow/scripts/deploy-development.sh [branch]
#
# Common examples:
#   bash scripts/deploy-development.sh agent/miniapp-shadcn-rework
#   DEV_DEPLOY_NO_CACHE=1 bash scripts/deploy-development.sh
#   DEV_DEPLOY_SERVICES="app nginx" bash scripts/deploy-development.sh
#
# Environment:
#   DEV_DEPLOY_BRANCH      Branch to deploy. Defaults to first argument, then current branch.
#   DEV_DEPLOY_RESET       1 = reset local tracked changes after saving a patch. Default: 1.
#   DEV_DEPLOY_CLEAN       1 = remove webapp/dist and webapp/node_modules before build. Default: 1.
#   DEV_DEPLOY_NODE_MODE   auto | local | docker. Default: auto.
#   DEV_DEPLOY_SERVICES    Optional compose services, for example "app nginx". Default: all services.
#   DEV_DEPLOY_NO_CACHE    1 = docker compose build --no-cache before up. Default: 0.
#   DEV_DEPLOY_PULL_IMAGES 1 = docker compose pull --ignore-buildable before up. Default: 0.
#   DEV_DEPLOY_HEALTH_URL  Optional URL to poll after compose up.
#   DEV_DEPLOY_LOCK_FILE   Lock file path. Default: /tmp/artflow-development-deploy.lock.

log() {
  printf '[artflow-dev-deploy] %s\n' "$*"
}

fail() {
  printf '[artflow-dev-deploy] ERROR: %s\n' "$*" >&2
  exit 1
}

on_error() {
  local exit_code=$?
  local line_number="${1:-unknown}"
  printf '[artflow-dev-deploy] ERROR: failed at line %s with exit code %s\n' \
    "$line_number" "$exit_code" >&2

  if [ -n "${APP_DIR:-}" ] && [ -d "$APP_DIR" ]; then
    cd "$APP_DIR" || true
    docker compose ps >&2 || true
    docker compose logs --tail=120 app nginx >&2 || true
  fi

  exit "$exit_code"
}

trap 'on_error "$LINENO"' ERR

command -v git >/dev/null 2>&1 || fail "git is not installed"
command -v docker >/dev/null 2>&1 || fail "docker is not installed"
command -v flock >/dev/null 2>&1 || fail "flock is not installed"
docker compose version >/dev/null 2>&1 || fail "docker compose plugin is unavailable"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${DEV_DEPLOY_APP_DIR:-$SCRIPT_DIR/..}" && pwd)"
REPO_DIR="${DEV_DEPLOY_REPO_DIR:-$(git -C "$APP_DIR" rev-parse --show-toplevel)}"
APP_SUBDIR="${DEV_DEPLOY_APP_SUBDIR:-$(realpath --relative-to="$REPO_DIR" "$APP_DIR")}" 
WEBAPP_DIR="$APP_DIR/webapp"
LOCK_FILE="${DEV_DEPLOY_LOCK_FILE:-/tmp/artflow-development-deploy.lock}"
RESET_LOCAL="${DEV_DEPLOY_RESET:-1}"
CLEAN_WEBAPP="${DEV_DEPLOY_CLEAN:-1}"
NODE_MODE="${DEV_DEPLOY_NODE_MODE:-auto}"
NO_CACHE="${DEV_DEPLOY_NO_CACHE:-0}"
PULL_IMAGES="${DEV_DEPLOY_PULL_IMAGES:-0}"
HEALTH_URL="${DEV_DEPLOY_HEALTH_URL:-}"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  fail "another development deployment is already running"
fi

[ -d "$REPO_DIR/.git" ] || fail "$REPO_DIR is not a Git repository"
[ -d "$APP_DIR" ] || fail "$APP_DIR is missing"
[ -f "$APP_DIR/docker-compose.yml" ] || fail "$APP_DIR/docker-compose.yml is missing"
[ -f "$WEBAPP_DIR/package.json" ] || fail "$WEBAPP_DIR/package.json is missing"
[ -f "$WEBAPP_DIR/package-lock.json" ] || fail "$WEBAPP_DIR/package-lock.json is missing; run npm install once and commit the lockfile"

cd "$REPO_DIR"

CURRENT_BRANCH="$(git branch --show-current)"
TARGET_BRANCH="${1:-${DEV_DEPLOY_BRANCH:-$CURRENT_BRANCH}}"
[ -n "$TARGET_BRANCH" ] || fail "target branch is empty; pass a branch name"

PATCH_FILE=""
if ! git diff --quiet || ! git diff --cached --quiet; then
  PATCH_FILE="/tmp/artflow-dev-deploy-local-$(date +%Y%m%d-%H%M%S).patch"
  log "local tracked changes found; saving patch to $PATCH_FILE"
  git diff --binary > "$PATCH_FILE"
  git diff --cached --binary >> "$PATCH_FILE"

  if [ "$RESET_LOCAL" = "1" ]; then
    log "resetting tracked changes because DEV_DEPLOY_RESET=1"
    git reset --hard
  else
    fail "working tree has local changes. Saved patch: $PATCH_FILE. Set DEV_DEPLOY_RESET=1 to reset automatically"
  fi
fi

UNTRACKED_COUNT="$(git ls-files --others --exclude-standard | wc -l | tr -d ' ')"
if [ "$UNTRACKED_COUNT" != "0" ]; then
  log "untracked files exist; generated webapp files will be cleaned, other untracked files are left untouched"
  git ls-files --others --exclude-standard | sed 's/^/[artflow-dev-deploy]   untracked: /' >&2 || true
fi

log "fetching origin/$TARGET_BRANCH"
git fetch --prune origin "$TARGET_BRANCH"
REMOTE_SHA="$(git rev-parse "origin/$TARGET_BRANCH")"

if git show-ref --verify --quiet "refs/heads/$TARGET_BRANCH"; then
  if [ "$(git branch --show-current)" != "$TARGET_BRANCH" ]; then
    log "switching to existing branch $TARGET_BRANCH"
    git switch "$TARGET_BRANCH"
  fi
else
  log "creating local branch $TARGET_BRANCH from origin/$TARGET_BRANCH"
  git switch --track -c "$TARGET_BRANCH" "origin/$TARGET_BRANCH"
fi

LOCAL_SHA="$(git rev-parse HEAD)"
if [ "$LOCAL_SHA" != "$REMOTE_SHA" ]; then
  if [ "$RESET_LOCAL" = "1" ]; then
    log "making local branch exactly match origin/$TARGET_BRANCH"
    git reset --hard "$REMOTE_SHA"
  else
    log "fast-forwarding $TARGET_BRANCH"
    git pull --ff-only origin "$TARGET_BRANCH"
  fi
fi

DEPLOYED_SHA="$(git rev-parse HEAD)"
log "checked out $TARGET_BRANCH at $DEPLOYED_SHA"

if [ "$CLEAN_WEBAPP" = "1" ]; then
  log "cleaning webapp/dist and webapp/node_modules"
  rm -rf "$WEBAPP_DIR/dist" "$WEBAPP_DIR/node_modules"
fi

build_webapp_local() {
  command -v npm >/dev/null 2>&1 || return 1
  log "building webapp with local npm"
  cd "$WEBAPP_DIR"
  npm ci
  npm run build
}

build_webapp_docker() {
  log "building webapp with node:22-alpine container"
  docker run --rm \
    -v "$WEBAPP_DIR:/app" \
    -w /app \
    node:22-alpine \
    sh -lc 'npm ci && npm run build'
}

case "$NODE_MODE" in
  local)
    build_webapp_local
    ;;
  docker)
    build_webapp_docker
    ;;
  auto)
    if ! build_webapp_local; then
      log "local npm is unavailable; falling back to Docker Node"
      build_webapp_docker
    fi
    ;;
  *)
    fail "DEV_DEPLOY_NODE_MODE must be one of: auto, local, docker"
    ;;
esac

[ -f "$WEBAPP_DIR/dist/index.html" ] || fail "webapp build did not create dist/index.html"

log "built webapp bundle:"
find "$WEBAPP_DIR/dist" -maxdepth 2 -type f | sort | sed "s#^$APP_DIR/#[artflow-dev-deploy]   #"

cd "$APP_DIR"

log "validating Docker Compose configuration"
docker compose config --quiet

if [ "$PULL_IMAGES" = "1" ]; then
  log "pulling compose images"
  docker compose pull --ignore-buildable
fi

# Split optional services string safely enough for service names.
# shellcheck disable=SC2206
SERVICES=(${DEV_DEPLOY_SERVICES:-})

if [ "$NO_CACHE" = "1" ]; then
  log "building compose images without cache"
  if [ "${#SERVICES[@]}" -gt 0 ]; then
    docker compose build --no-cache "${SERVICES[@]}"
    docker compose up -d --remove-orphans "${SERVICES[@]}"
  else
    docker compose build --no-cache
    docker compose up -d --remove-orphans
  fi
else
  log "building and recreating compose services"
  if [ "${#SERVICES[@]}" -gt 0 ]; then
    docker compose up -d --build --remove-orphans "${SERVICES[@]}"
  else
    docker compose up -d --build --remove-orphans
  fi
fi

log "compose status"
docker compose ps

if [ -n "$HEALTH_URL" ]; then
  command -v curl >/dev/null 2>&1 || fail "curl is required for DEV_DEPLOY_HEALTH_URL"
  log "checking health URL: $HEALTH_URL"
  for attempt in $(seq 1 30); do
    if curl --fail --silent --show-error --max-time 10 "$HEALTH_URL" >/dev/null; then
      log "health check passed"
      break
    fi
    if [ "$attempt" = "30" ]; then
      docker compose logs --tail=120 app nginx >&2 || true
      fail "health check did not pass: $HEALTH_URL"
    fi
    sleep 3
  done
fi

if [ -n "$PATCH_FILE" ]; then
  log "local changes patch saved at $PATCH_FILE"
fi

log "development deployment completed at $DEPLOYED_SHA"
