#!/usr/bin/env bash
set -euo pipefail

OUT="artflow_context_$(date +%Y%m%d_%H%M%S).txt"

GREEN="\033[0;32m"
YELLOW="\033[1;33m"
NC="\033[0m"

section() {
  {
    echo
    echo "============================================================"
    echo "$1"
    echo "============================================================"
    echo
  } >> "$OUT"
}

file_dump() {
  local path="$1"

  if [ -f "$path" ]; then
    {
      echo
      echo "---------------- FILE: $path ----------------"
      cat "$path"
      echo
      echo "---------------- END FILE: $path ----------------"
      echo
    } >> "$OUT"
  else
    {
      echo
      echo "---------------- MISSING FILE: $path ----------------"
      echo
    } >> "$OUT"
  fi
}

echo -e "${YELLOW}Collecting artflow context...${NC}"

{
  echo "ARTFLOW CONTEXT SNAPSHOT"
  echo "Generated at: $(date -Is)"
  echo "Host: $(hostname 2>/dev/null || true)"
  echo "User: $(whoami 2>/dev/null || true)"
  echo "PWD: $(pwd)"
} > "$OUT"

section "GIT INFO"
{
  git rev-parse --show-toplevel 2>/dev/null || true
  git status --short 2>/dev/null || true
  echo
  git branch --show-current 2>/dev/null || true
  git log -5 --oneline 2>/dev/null || true
  echo
  git remote -v 2>/dev/null || true
} >> "$OUT"

section "PROJECT TREE"
{
  find . -maxdepth 5 -type f \
    ! -path "*/.git/*" \
    ! -path "*/__pycache__/*" \
    ! -path "*/.pytest_cache/*" \
    ! -path "*/.mypy_cache/*" \
    ! -path "*/venv/*" \
    ! -path "*/.venv/*" \
    ! -path "*/node_modules/*" \
    ! -path "*/logs/*" \
    ! -name "*.pyc" \
    ! -name "artflow_context_*.txt" \
    | sort
} >> "$OUT"

section "IMPORTANT FILES"

FILES=(
  "main.py"
  ".env.example"
  "requirements.txt"
  "docker-compose.yml"
  "Dockerfile"
  "alembic.ini"

  "core/config.py"
  "core/logger.py"

  "db/models.py"
  "db/repository.py"
  "db/session.py"
  "db/seed.py"

  "bot/states/__init__.py"
  "bot/handlers/image_gen.py"
  "bot/handlers/video_gen.py"
  "bot/handlers/midjourney.py"
  "bot/handlers/start.py"
  "bot/handlers/balance.py"
  "bot/handlers/payment.py"
  "bot/handlers/admin.py"
  "bot/handlers/marketplace.py"

  "bot/keyboards/models.py"
  "bot/keyboards/main_menu.py"

  "bot/middlewares/auth.py"
  "bot/middlewares/db.py"
  "bot/middlewares/throttling.py"

  "api/image_service.py"
  "api/video_service.py"
  "api/polling.py"
  "api/comet_client.py"

  "payments/tbank.py"
  "payments/cryptobot.py"
)

for f in "${FILES[@]}"; do
  file_dump "$f"
done

section "MIGRATIONS"
{
  if [ -d "db/migrations" ]; then
    find db/migrations -maxdepth 4 -type f | sort
  elif [ -d "alembic" ]; then
    find alembic -maxdepth 4 -type f | sort
  elif [ -d "migrations" ]; then
    find migrations -maxdepth 4 -type f | sort
  else
    echo "No obvious migrations directory found."
  fi
} >> "$OUT"

if [ -d "db/migrations" ]; then
  while IFS= read -r f; do file_dump "$f"; done < <(find db/migrations -maxdepth 4 -type f | sort)
fi

if [ -d "alembic" ]; then
  while IFS= read -r f; do file_dump "$f"; done < <(find alembic -maxdepth 4 -type f | sort)
fi

if [ -d "migrations" ]; then
  while IFS= read -r f; do file_dump "$f"; done < <(find migrations -maxdepth 4 -type f | sort)
fi

section "SEARCH: IMAGE SESSION / GENERATION / CALLBACKS"
{
  grep -RIn \
    -E "ImageGenFSM|Generation|create_generation|finish_generation|image_model|img_model|img_ratio|img_quality|after_generation|reference|remix|repeat|animate|video|referral|referrer|session_active|image_session" \
    . \
    --exclude-dir=.git \
    --exclude-dir=__pycache__ \
    --exclude-dir=.venv \
    --exclude-dir=venv \
    --exclude="*.pyc" \
    --exclude="artflow_context_*.txt" \
    2>/dev/null || true
} >> "$OUT"

section "PYTHON AST CHECK"
{
  python - <<'PY' || true
import ast
from pathlib import Path

files = [
    "main.py",
    "db/models.py",
    "db/repository.py",
    "bot/states/__init__.py",
    "bot/handlers/image_gen.py",
    "bot/keyboards/models.py",
    "api/image_service.py",
    "api/video_service.py",
]

for f in files:
    p = Path(f)
    if not p.exists():
        print(f"MISSING: {f}")
        continue
    try:
        ast.parse(p.read_text(encoding="utf-8"))
        print(f"OK AST: {f}")
    except Exception as e:
        print(f"BAD AST: {f}: {e}")
PY
} >> "$OUT"

section "ENV EXAMPLE KEYS ONLY"
{
  if [ -f ".env.example" ]; then
    sed -E 's/(=).*/=***MASKED***/' .env.example
  else
    echo ".env.example not found"
  fi
} >> "$OUT"

echo
echo -e "${GREEN}Done:${NC} $OUT"
echo "Перед отправкой проверь, что в файле нет реальных секретов:"
echo "grep -Ein 'token|secret|password|api_key|apikey|key' $OUT"
