#!/usr/bin/env bash
# 平台 PostgreSQL 在本机 Docker 与远程依赖服务器之间迁移
#
# 用法:
#   bash scripts/migrate-postgres.sh to-local    # 远程 → 本机（混合 remote-dev）
#   bash scripts/migrate-postgres.sh to-remote   # 本机 → 远程（全远程依赖）
#
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

step() { echo "→ $*"; }

ensure_local_postgres() {
  step "启动本机 PostgreSQL（:${LOCAL_POSTGRES_PORT}）…"
  LOCAL_POSTGRES_PORT="$LOCAL_POSTGRES_PORT" \
    docker compose -f configs/compose/compose.yaml up -d postgres
  step "等待本机 postgres 健康…"
  local _
  for _ in $(seq 1 30); do
    if docker compose -f configs/compose/compose.yaml ps postgres 2>/dev/null | grep -q healthy; then
      break
    fi
    sleep 2
  done
}

cmd_to_local() {
  local DUMP_FILE="$MIGRATION_DIR/platform_remote_${STAMP}.dump"
  mkdir -p "$MIGRATION_DIR"
  ensure_local_postgres

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
    echo "  1) 服务器: docker compose -p benxi restart postgres"
    echo "  2) 或在服务器本机导出后 scp 到本机 ${MIGRATION_DIR}/"
    echo "  3) 若本机 data/postgres 已有数据，可仅: bash scripts/setup-env.sh local-db"
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
  docker compose -f configs/compose/compose.yaml exec -T postgres \
    psql -U "$PG_USER" -d "$PG_DB" -c \
    "SELECT 'users' AS tbl, count(*) FROM users UNION ALL SELECT 'documents', count(*) FROM documents;"

  echo ""
  echo "迁移完成: ${DUMP_FILE}"
  echo "下一步: bash scripts/setup-env.sh local-db && ./dev.sh local restart"
}

cmd_to_remote() {
  local DUMP_FILE="$MIGRATION_DIR/platform_local_${STAMP}.dump"
  mkdir -p "$MIGRATION_DIR"

  if ! docker compose -f configs/compose/compose.yaml ps postgres 2>/dev/null | grep -qE 'running|healthy'; then
    ensure_local_postgres
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
    echo "  2) 服务器: docker compose -p benxi restart postgres"
    echo "  3) 本机重试: bash scripts/migrate-postgres.sh to-remote"
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
  echo "  REMOTE_HOST=${REMOTE_HOST} bash scripts/setup-env.sh remote-dev"
  echo "  ./dev.sh local restart"
  echo "可选：停止本机 postgres"
  echo "  docker compose -f configs/compose/compose.yaml stop postgres"
}

usage() {
  cat <<EOF
用法: bash scripts/migrate-postgres.sh <方向>

  to-local    远程平台库 → 本机 Docker postgres
  to-remote   本机 Docker postgres → 远程平台库

示例:
  bash scripts/migrate-postgres.sh to-local
  REMOTE_HOST=172.19.134.45 bash scripts/migrate-postgres.sh to-remote
EOF
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    to-local) cmd_to_local ;;
    to-remote) cmd_to_remote ;;
    -h|--help|help) usage ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "${1:-}"
