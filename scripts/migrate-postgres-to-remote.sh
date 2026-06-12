#!/usr/bin/env bash
# 将本机 Docker PostgreSQL 导出并导入远程平台库（remote-dev 全远程依赖）
#
# 用法:
#   bash scripts/migrate-postgres-to-remote.sh
#   REMOTE_HOST=172.19.134.45 LOCAL_POSTGRES_PORT=5432 bash scripts/migrate-postgres-to-remote.sh
#
# 前置:
#   - 本机 postgres 容器在跑（compose.local-db.yaml）
#   - 远程 40002 可 pg_restore（服务器内存充足；僵死时 restart postgres）
# 完成后:
#   REMOTE_HOST=172.19.134.45 bash scripts/setup-remote-dev-env.sh
#   ./dev.sh local restart
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REMOTE_HOST="${REMOTE_HOST:-172.19.134.45}"
REMOTE_POSTGRES_PORT="${REMOTE_POSTGRES_PORT:-40002}"
LOCAL_POSTGRES_PORT="${LOCAL_POSTGRES_PORT:-5432}"
PG_USER="${POSTGRES_USER:-platform}"
PG_PASS="${POSTGRES_PASSWORD:-platform}"
PG_DB="${POSTGRES_DB:-platform}"
PG_IMAGE="${POSTGRES_IMAGE:-postgres:16-alpine}"

MIGRATION_DIR="$ROOT/.run/migration"
STAMP="$(date +%Y%m%d%H%M%S)"
DUMP_FILE="$MIGRATION_DIR/platform_local_${STAMP}.dump"

mkdir -p "$MIGRATION_DIR"

step() { echo "→ $*"; }

if ! docker compose -f compose.yaml -f compose.local-db.yaml ps postgres 2>/dev/null | grep -qE 'running|healthy'; then
  step "启动本机 PostgreSQL（:${LOCAL_POSTGRES_PORT}）…"
  LOCAL_POSTGRES_PORT="$LOCAL_POSTGRES_PORT" \
    docker compose -f compose.yaml -f compose.local-db.yaml up -d postgres
  for _ in $(seq 1 30); do
    if docker compose -f compose.yaml -f compose.local-db.yaml ps postgres 2>/dev/null | grep -q healthy; then
      break
    fi
    sleep 2
  done
fi

step "从本机导出 127.0.0.1:${LOCAL_POSTGRES_PORT}/${PG_DB} …"
docker run --rm \
  -e PGPASSWORD="$PG_PASS" \
  -v "$MIGRATION_DIR:/backup" \
  --add-host=host.docker.internal:host-gateway \
  "$PG_IMAGE" \
  pg_dump \
  -h host.docker.internal \
  -p "$LOCAL_POSTGRES_PORT" \
  -U "$PG_USER" \
  -d "$PG_DB" \
  -Fc \
  --no-owner \
  --no-acl \
  -f "/backup/$(basename "$DUMP_FILE")"

step "导入远程 ${REMOTE_HOST}:${REMOTE_POSTGRES_PORT}/${PG_DB}（--clean --if-exists）…"
if ! docker run --rm \
  -e PGPASSWORD="$PG_PASS" \
  -v "$MIGRATION_DIR:/backup" \
  "$PG_IMAGE" \
  pg_restore \
  -h "$REMOTE_HOST" \
  -p "$REMOTE_POSTGRES_PORT" \
  -U "$PG_USER" \
  -d "$PG_DB" \
  --clean \
  --if-exists \
  --no-owner \
  --no-acl \
  "/backup/$(basename "$DUMP_FILE")" \
  || true; then
  echo ""
  echo "远程 pg_restore 失败（常见：服务器 postgres 僵死或内存不足）。"
  echo "  1) 服务器释放内存: docker stats；必要时 bash scripts/server-add-swap.sh"
  echo "  2) 服务器: docker compose -p lvye restart postgres"
  echo "  3) 本机重试: bash scripts/migrate-postgres-to-remote.sh"
  exit 1
fi

step "校验远程库（通过本机 TCP）…"
docker run --rm \
  -e PGPASSWORD="$PG_PASS" \
  "$PG_IMAGE" \
  psql \
  -h "$REMOTE_HOST" \
  -p "$REMOTE_POSTGRES_PORT" \
  -U "$PG_USER" \
  -d "$PG_DB" \
  -c "SELECT 'users' AS tbl, count(*) FROM users UNION ALL SELECT 'documents', count(*) FROM documents;"

echo ""
echo "迁移完成: ${DUMP_FILE}"
echo "下一步:"
echo "  REMOTE_HOST=${REMOTE_HOST} bash scripts/setup-remote-dev-env.sh"
echo "  ./dev.sh local restart"
echo "可选：停止本机 postgres 释放资源"
echo "  docker compose -f compose.yaml -f compose.local-db.yaml stop postgres"
