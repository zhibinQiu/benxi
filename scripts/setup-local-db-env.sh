#!/usr/bin/env bash
# 混合 remote-dev：本机 PostgreSQL + 远程 Redis / MinIO / KnowFlow 等
#
# 用法:
#   bash scripts/setup-local-db-env.sh
#   LOCAL_POSTGRES_PORT=5432 bash scripts/setup-local-db-env.sh
#
# 数据迁移（远程可用时）:
#   bash scripts/migrate-postgres-to-local.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="$ROOT/platform"
OUT="$PLATFORM/.env"
LOCAL_POSTGRES_PORT="${LOCAL_POSTGRES_PORT:-5432}"
LOCAL_DB_URL="postgresql+psycopg2://platform:platform@127.0.0.1:${LOCAL_POSTGRES_PORT}/platform"

if [[ ! -f "$OUT" ]]; then
  echo "缺少 ${OUT}，请先运行: bash scripts/setup-remote-dev-env.sh" >&2
  exit 1
fi

sed_inplace() {
  if sed --version 2>/dev/null | grep -q GNU; then
    sed -i "$@"
  else
    sed -i '' "$@"
  fi
}

BACKUP="$PLATFORM/.env.local-backup-$(date +%Y%m%d%H%M%S)"
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
echo "应用 schema 补丁（旧库首次切换时建议执行一次）:"
echo "  cd platform && .venv/bin/python -c 'from app.main import _bootstrap_database; _bootstrap_database()'"
echo "启动开发栈:"
echo "  ./dev.sh local"
