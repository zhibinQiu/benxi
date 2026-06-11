#!/usr/bin/env bash
# 将远程平台 PostgreSQL 导出并导入本机 Docker postgres（混合 remote-dev：本机 PG + 远程 Redis/MinIO/KnowFlow）
#
# 用法:
#   bash scripts/migrate-postgres-to-local.sh
#   REMOTE_HOST=172.19.134.45 LOCAL_POSTGRES_PORT=5432 bash scripts/migrate-postgres-to-local.sh
#
# 前置: 远程 40002 可完成 pg_dump（TCP 通但握手超时则需先在服务器 restart postgres）
# 完成后: bash scripts/setup-local-db-env.sh && ./dev.sh local restart
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
DUMP_FILE="$MIGRATION_DIR/platform_remote_${STAMP}.dump"

mkdir -p "$MIGRATION_DIR"

step() { echo "→ $*"; }

step "启动本机 PostgreSQL（:${LOCAL_POSTGRES_PORT}）…"
LOCAL_POSTGRES_PORT="$LOCAL_POSTGRES_PORT" \
  docker compose -f compose.yaml -f compose.local-db.yaml up -d postgres

step "等待本机 postgres 健康…"
for _ in $(seq 1 30); do
  if docker compose -f compose.yaml -f compose.local-db.yaml ps postgres 2>/dev/null | grep -q healthy; then
    break
  fi
  sleep 2
done

step "从远程导出 ${REMOTE_HOST}:${REMOTE_POSTGRES_PORT}/${PG_DB} …"
if ! docker run --rm \
  -e PGPASSWORD="$PG_PASS" \
  -v "$MIGRATION_DIR:/backup" \
  "$PG_IMAGE" \
  pg_dump \
  -h "$REMOTE_HOST" \
  -p "$REMOTE_POSTGRES_PORT" \
  -U "$PG_USER" \
  -d "$PG_DB" \
  -Fc \
  --no-owner \
  --no-acl \
  -f "/backup/$(basename "$DUMP_FILE")"; then
  echo ""
  echo "远程 pg_dump 失败（常见：TCP 通但 PostgreSQL 握手/查询超时）。"
  echo "  1) 服务器: docker compose -p lvye restart postgres"
  echo "  2) 或在服务器本机导出后 scp 到本机 ${MIGRATION_DIR}/"
  echo "  3) 若本机 data/postgres 已有数据，可仅执行: bash scripts/setup-local-db-env.sh"
  exit 1
fi

step "导入本机 postgres（--clean --if-exists）…"
docker run --rm \
  -e PGPASSWORD="$PG_PASS" \
  -v "$MIGRATION_DIR:/backup" \
  --add-host=host.docker.internal:host-gateway \
  "$PG_IMAGE" \
  pg_restore \
  -h host.docker.internal \
  -p "$LOCAL_POSTGRES_PORT" \
  -U "$PG_USER" \
  -d "$PG_DB" \
  --clean \
  --if-exists \
  --no-owner \
  --no-acl \
  "/backup/$(basename "$DUMP_FILE")" \
  || true

step "校验本机库…"
docker compose -f compose.yaml -f compose.local-db.yaml exec -T postgres \
  psql -U "$PG_USER" -d "$PG_DB" -c \
  "SELECT 'users' AS tbl, count(*) FROM users UNION ALL SELECT 'documents', count(*) FROM documents;"

echo ""
echo "迁移完成: ${DUMP_FILE}"
echo "下一步: bash scripts/setup-local-db-env.sh && ./dev.sh local restart"
