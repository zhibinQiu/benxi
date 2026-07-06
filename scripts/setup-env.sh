#!/usr/bin/env bash
# 生成本地开发用 backend/.env（remote-dev / 本机 PostgreSQL）
#
# 用法:
#   bash scripts/setup-env.sh remote-dev
#   bash scripts/setup-env.sh local-db
#   LOCAL_POSTGRES_PORT=5432 bash scripts/setup-env.sh local-db
#
# 入口: ./dev.sh remote-dev  →  remote-dev
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/envfile.sh
source "$SCRIPT_DIR/lib/envfile.sh"

PLATFORM="$ROOT/backend"
REMOTE_HOST="${REMOTE_HOST:-172.19.134.45}"

REMOTE_DEV_KEYS=(
  JWT_SECRET DEEPSEEK_API_KEY DEEPSEEK_BASE_URL DEEPSEEK_MODEL
  BOOTSTRAP_ADMIN_PHONE BOOTSTRAP_ADMIN_PASSWORD BOOTSTRAP_ADMIN_USERNAME BOOTSTRAP_ADMIN_EMAIL
  ACCESS_TOKEN_EXPIRE_MINUTES SMART_DATA_QUERY_V2_DIFY_API_KEY CARBON_QA_V2_CHAT_API_KEY
  PLATFORM_LLM_API_KEY PLATFORM_LLM_BASE_URL PLATFORM_LLM_MODEL
  PLATFORM_EMBEDDING_API_KEY PLATFORM_EMBEDDING_BASE_URL PLATFORM_EMBEDDING_MODEL PLATFORM_EMBEDDING_FACTORY
  PLATFORM_VL_API_KEY PLATFORM_VL_BASE_URL PLATFORM_VL_MODEL
  PLATFORM_RERANK_API_KEY PLATFORM_RERANK_BASE_URL PLATFORM_RERANK_MODEL
  PLATFORM_PADDLEOCR_BASE_URL PLATFORM_PADDLEOCR_API_KEY PLATFORM_PADDLEOCR_MODEL
  PLATFORM_PADDLEOCR_URL RAGFLOW_API_KEY
  RAGFLOW_SHARED_EMAIL RAGFLOW_SHARED_PASSWORD
  RAGFLOW_LLM_TEMPLATE_EMAIL SMART_DATA_QUERY_PATH CARBON_QA_PATH
  SMART_FORECAST_PROXY_PREFIX
)

cmd_remote_dev() {
  local SRC="$PLATFORM/.env.remote.example"
  local OUT="$PLATFORM/.env"
  if [[ ! -f "$SRC" ]]; then
    echo "缺少 $SRC" >&2
    exit 1
  fi

  local OLD_BACKUP=""
  if [[ -f "$OUT" ]]; then
    OLD_BACKUP="$(mktemp)"
    cp "$OUT" "$OLD_BACKUP"
  fi

  cp "$SRC" "$OUT"
  sed_inplace "s|172\\.19\\.134\\.45|${REMOTE_HOST}|g" "$OUT"
  sed_inplace "s|^REMOTE_HOST=.*|REMOTE_HOST=${REMOTE_HOST}|" "$OUT"

  if [[ -n "$OLD_BACKUP" ]]; then
    local key
    for key in "${REMOTE_DEV_KEYS[@]}"; do
      envfile_merge_key "$key" "$OUT" "$OLD_BACKUP"
    done
    rm -f "$OLD_BACKUP"
  fi

  echo "已生成 ${OUT}（REMOTE_HOST=${REMOTE_HOST}）"
  echo "验证远程依赖: bash scripts/verify-remote-deps.sh"
  echo "同步资源配置菜单: cd platform && python scripts/sync_resource_settings_from_env.py --force"
  echo "启动本机 dev: ./dev.sh local"
}

cmd_local_db() {
  local OUT="$PLATFORM/.env"
  local LOCAL_POSTGRES_PORT="${LOCAL_POSTGRES_PORT:-5432}"
  local LOCAL_DB_URL="postgresql+psycopg2://platform:platform@127.0.0.1:${LOCAL_POSTGRES_PORT}/platform"

  if [[ ! -f "$OUT" ]]; then
    echo "缺少 ${OUT}，请先: ./dev.sh remote-dev  或  bash scripts/setup-env.sh remote-dev" >&2
    exit 1
  fi

  local BACKUP="$PLATFORM/.env.local-backup-$(date +%Y%m%d%H%M%S)"
  cp "$OUT" "$BACKUP"

  sed_inplace "s|^DATABASE_URL=.*|DATABASE_URL=${LOCAL_DB_URL}|" "$OUT"

  if grep -qE '^LOCAL_POSTGRES_PORT=' "$OUT"; then
    sed_inplace "s|^LOCAL_POSTGRES_PORT=.*|LOCAL_POSTGRES_PORT=${LOCAL_POSTGRES_PORT}|" "$OUT"
  else
    printf '\n# 本机 PostgreSQL（compose.local-db.yaml）\nLOCAL_POSTGRES_PORT=%s\n' "$LOCAL_POSTGRES_PORT" >>"$OUT"
  fi

  echo "已切换为本机 PostgreSQL（保留 REMOTE_DEPS 与其余远程依赖）"
  echo "  备份: ${BACKUP}"
  echo "  DATABASE_URL=${LOCAL_DB_URL}"
  echo ""
  echo "启动本机 postgres:"
  echo "  LOCAL_POSTGRES_PORT=${LOCAL_POSTGRES_PORT} docker compose -f compose.yaml -f compose.local-db.yaml up -d postgres"
  echo "数据迁移（远程可用时）:"
  echo "  bash scripts/migrate-postgres.sh to-local"
  echo "启动开发栈:"
  echo "  ./dev.sh local"
}

usage() {
  cat <<EOF
用法: bash scripts/setup-env.sh <子命令>

  remote-dev   生成本机 + 远程依赖 backend/.env（REMOTE_DEPS=1）
  local-db     DATABASE_URL 指向本机 Docker postgres

示例:
  REMOTE_HOST=172.19.134.45 bash scripts/setup-env.sh remote-dev
  bash scripts/migrate-postgres.sh to-local && bash scripts/setup-env.sh local-db
EOF
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    remote-dev) cmd_remote_dev ;;
    local-db) cmd_local_db ;;
    -h|--help|help) usage ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "${1:-}"
