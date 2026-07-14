#!/usr/bin/env bash
# KnowFlow 解析队列重置：清空积压 task、重置卡住文档、重启 ragflow（含 task_executor）
#
#   bash scripts/knowflow-queue-reset.sh              # 远程服务器（deploy.target）
#   bash scripts/knowflow-queue-reset.sh --local       # 本机 Docker 栈
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
info()  { echo -e "${GREEN}[knowflow-reset]${NC} $*"; }
warn()  { echo -e "${YELLOW}[knowflow-reset]${NC} $*"; }
error() { echo -e "${RED}[knowflow-reset]${NC} $*" >&2; }

LOCAL=0
DEDUPE=0
for arg in "$@"; do
  case "$arg" in
    --local) LOCAL=1 ;;
    --dedupe) DEDUPE=1 ;;
  esac
done

MYSQL_PASSWORD="${MYSQL_PASSWORD:-infini_rag_flow}"
MYSQL_DB="${MYSQL_DB:-rag_flow}"
REDIS_PASSWORD="${REDIS_PASSWORD:-infini_rag_flow}"
COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-benxi}"

run_remote() {
  DEPLOY_USER="${DEPLOY_USER:-root}"
  DEPLOY_HOST="${DEPLOY_HOST:-172.19.134.45}"
  DEPLOY_PATH="${DEPLOY_PATH:-/root/qzb/benxi}"
  if [[ -f "$ROOT/backend/deploy.target" ]]; then
    # shellcheck disable=SC1091
    source "$ROOT/backend/deploy.target"
  fi
  info "远程执行 → ${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}"
  ssh "${DEPLOY_USER}@${DEPLOY_HOST}" \
    "MYSQL_PASSWORD='${MYSQL_PASSWORD}' MYSQL_DB='${MYSQL_DB}' REDIS_PASSWORD='${REDIS_PASSWORD}' COMPOSE_PROJECT='${COMPOSE_PROJECT}' DEDUPE='${DEDUPE}' DEPLOY_PATH='${DEPLOY_PATH}'" \
    bash -s <<'REMOTE'
set -euo pipefail
cd "${DEPLOY_PATH:-/root/qzb/benxi}"
COMPOSE=(docker compose -p "${COMPOSE_PROJECT:-benxi}" -f configs/compose/compose.yaml -f third_party/deploy/knowflow.yml)

info() { echo "[knowflow-reset] $*"; }

info "1/4 停止 ragflow（task_executor 随容器停止）"
"${COMPOSE[@]}" stop ragflow 2>/dev/null || true

info "2/4 清空 MySQL 解析 task（待处理/进行中/失败）并重置解析中文档"
"${COMPOSE[@]}" exec -T knowflow-mysql mysql -uroot -p"${MYSQL_PASSWORD}" "${MYSQL_DB}" <<SQL
DELETE FROM task WHERE progress < 1 OR progress IS NULL;
UPDATE document SET run = '0', progress = 0, progress_msg = NULL WHERE run IN ('0', '1', '4');
SQL

info "3/4 清空 Redis 解析队列 stream"
for q in rag_flow_svr_queue rag_flow_svr_queue_1; do
  "${COMPOSE[@]}" exec -T redis redis-cli -a "${REDIS_PASSWORD}" DEL "$q" 2>/dev/null || true
done

info "4/4 重启 ragflow"
"${COMPOSE[@]}" up -d ragflow
"${COMPOSE[@]}" ps ragflow

if [[ "${DEDUPE:-0}" == "1" ]]; then
  info "5/5 清理重复 document（保留每组最新已完成或最新创建）"
  python3 scripts/knowflow-dedupe-documents.py --apply || warn "去重脚本需在仓库根目录执行，可本机: bash scripts/knowflow-queue-reset.sh --dedupe"
fi

info "完成。可在系统监控查看 queue_lag / pending_tasks。"
REMOTE
}

run_local() {
  info "本机 Docker 栈重置"
  COMPOSE=(docker compose -p "${COMPOSE_PROJECT}" -f configs/compose/compose.yaml -f third_party/deploy/knowflow.yml)
  "${COMPOSE[@]}" stop ragflow 2>/dev/null || true
  "${COMPOSE[@]}" exec -T knowflow-mysql mysql -uroot -p"${MYSQL_PASSWORD}" "${MYSQL_DB}" <<SQL
DELETE FROM task WHERE progress < 1 OR progress IS NULL;
UPDATE document SET run = '0', progress = 0, progress_msg = NULL WHERE run IN ('0', '1', '4');
SQL
  for q in rag_flow_svr_queue rag_flow_svr_queue_1; do
    docker compose -p "${COMPOSE_PROJECT}" exec -T redis redis-cli -a "${REDIS_PASSWORD}" DEL "$q" 2>/dev/null || true
  done
  "${COMPOSE[@]}" up -d ragflow
  if [[ "$DEDUPE" == 1 ]]; then
    python3 "$ROOT/scripts/knowflow-dedupe-documents.py" --apply
  fi
}

if [[ "$LOCAL" == 1 ]]; then
  run_local
else
  run_remote
fi
