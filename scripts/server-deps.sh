#!/usr/bin/env bash
# 远程依赖栈：服务器跑 Postgres/Redis/MinIO/KnowFlow 等，本机跑 API+前端
#
#   bash scripts/server-deps.sh sync
#   bash scripts/server-deps.sh up
#   bash scripts/server-deps.sh down
#   bash scripts/server-deps.sh status
#   bash scripts/server-deps.sh cleanup
#
# 编排统一走 scripts/stack.sh（EXPOSE_DEPS=1 + compose.expose-deps.yaml）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=lib/version.sh
source "$ROOT/scripts/lib/version.sh"
DEFAULT_VER="$(read_repo_version "$ROOT")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
info()  { echo -e "${GREEN}[server-deps]${NC} $*"; }
warn()  { echo -e "${YELLOW}[server-deps]${NC} $*"; }
error() { echo -e "${RED}[server-deps]${NC} $*" >&2; }

DEPLOY_USER="${DEPLOY_USER:-root}"
DEPLOY_HOST="${DEPLOY_HOST:-172.19.134.45}"
DEPLOY_PATH="${DEPLOY_PATH:-/root/qzb/lvye}"

if [[ -f "$ROOT/platform/deploy.target" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/platform/deploy.target"
fi

DEPS_SERVICES=(
  postgres redis minio pdf2zh-api speech-api
  knowflow-mysql knowflow-infinity knowflow-gotenberg ragflow knowflow-backend
)

remote_shell() {
  ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "DEPLOY_PATH='${DEPLOY_PATH}'" bash -s
}

cmd_push_images() {
  warn "服务器为 amd64 时请用 build-images（本机 arm64 镜像无法运行）"
  info "导入 pdf2zh + speech 镜像 → ${DEPLOY_HOST}"
  for img in "zhitan-pdf2zh:${ZHITAN_VERSION:-${DEFAULT_VER}}" "zhitan-speech:${ZHITAN_VERSION:-${DEFAULT_VER}}"; do
    docker image inspect "$img" >/dev/null 2>&1 || {
      error "本机缺少镜像 $img，请: bash scripts/server-deps.sh build-images"
      exit 1
    }
  done
  info "传输中（约 5GB）…"
  docker save "zhitan-pdf2zh:${ZHITAN_VERSION:-${DEFAULT_VER}}" "zhitan-speech:${ZHITAN_VERSION:-${DEFAULT_VER}}" \
    | ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "docker load"
  info "镜像导入完成"
}

cmd_rebuild_amd64() {
  info "服务器 amd64 重建 pdf2zh / speech（复用 zhitanAI 源码与模型）"
  cmd_sync
  rsync -avz --exclude '.venv' --exclude '__pycache__' \
    "$ROOT/platform/speech-service/" \
    "${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/build/speech-service/"
  remote_shell <<'REMOTE'
set -euo pipefail
cd "${DEPLOY_PATH:-/root/qzb/lvye}"
ver="${ZHITAN_VERSION:-3.9.3}"
mkdir -p data/speech-models data/pdf2zh-config

docker rmi -f "zhitan-pdf2zh:${ver}" "zhitan-speech:${ver}" 2>/dev/null || true

if [[ -d /root/qzb/zhitanAI/.run/speech-models ]]; then
  echo "[server-deps] 复用语音模型缓存 …"
  cp -a /root/qzb/zhitanAI/.run/speech-models/. data/speech-models/
fi
if docker volume inspect zhitanai_pdf2zh_config >/dev/null 2>&1; then
  docker run --rm -v zhitanai_pdf2zh_config:/from -v "$(pwd)/data/pdf2zh-config":/to alpine cp -a /from/. /to/ 2>/dev/null || true
fi

echo "[server-deps] 构建 speech (amd64) …"
docker build -t "zhitan-speech:${ver}-amd64" \
  --build-arg PYTHON_IMAGE=docker.1ms.run/library/python:3.11-slim \
  build/speech-service

echo "[server-deps] 构建 pdf2zh (amd64，首次约 20–40 分钟) …"
cd "${DEPLOY_PATH}"
bash scripts/stack.sh build pdf2zh-api
docker tag "zhitan-pdf2zh:${ver}" "zhitan-pdf2zh:${ver}-amd64" 2>/dev/null || \
  docker tag "$(docker images --format '{{.Repository}}:{{.Tag}}' | grep zhitan-pdf2zh | head -1)" "zhitan-pdf2zh:${ver}-amd64"

grep -q '^PDF2ZH_IMAGE=' .env && sed -i "s|^PDF2ZH_IMAGE=.*|PDF2ZH_IMAGE=zhitan-pdf2zh:${ver}-amd64|" .env || echo "PDF2ZH_IMAGE=zhitan-pdf2zh:${ver}-amd64" >> .env
grep -q '^SPEECH_IMAGE=' .env && sed -i "s|^SPEECH_IMAGE=.*|SPEECH_IMAGE=zhitan-speech:${ver}-amd64|" .env || echo "SPEECH_IMAGE=zhitan-speech:${ver}-amd64" >> .env
echo "[server-deps] amd64 镜像就绪"
REMOTE
  info "重建完成，执行: bash scripts/server-deps.sh up"
}

cmd_build_images() {
  info "同步构建上下文 → ${DEPLOY_HOST}:${DEPLOY_PATH}/build"
  ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "mkdir -p '${DEPLOY_PATH}/build/speech-service' '${DEPLOY_PATH}/build/pdf2zh'"
  rsync -avz --exclude '.venv' --exclude '__pycache__' \
    "$ROOT/platform/speech-service/" \
    "${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/build/speech-service/"
  rsync -avz \
    "$ROOT/Dockerfile" "$ROOT/pyproject.toml" "$ROOT/uv.lock" \
    "${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/build/pdf2zh/" 2>/dev/null || \
  rsync -avz "$ROOT/Dockerfile" "${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/build/pdf2zh/"
  remote_shell <<'REMOTE'
set -euo pipefail
cd "${DEPLOY_PATH:-/root/qzb/lvye}"
ver="${ZHITAN_VERSION:-3.9.3}"
mkdir -p data/speech-models data/pdf2zh-config
if [[ -d /root/qzb/zhitanAI/.run/speech-models ]] && [[ -z "$(ls -A data/speech-models 2>/dev/null)" ]]; then
  cp -a /root/qzb/zhitanAI/.run/speech-models/. data/speech-models/
fi
echo "[server-deps] 构建 zhitan-speech:${ver} (amd64) …"
docker build -t "zhitan-speech:${ver}" build/speech-service
echo "[server-deps] 构建 zhitan-pdf2zh:${ver} (amd64，首次较慢) …"
bash scripts/stack.sh build pdf2zh-api
echo "[server-deps] amd64 镜像构建完成"
REMOTE
  info "构建完成，执行: bash scripts/server-deps.sh up"
}

cmd_sync() {
  info "同步 → ${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}"
  ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "mkdir -p '${DEPLOY_PATH}/scripts' '${DEPLOY_PATH}/data'"
  rsync -avz \
    "$ROOT/compose.yaml" \
    "$ROOT/compose.mirror.yaml" \
    "$ROOT/compose.expose-deps.yaml" \
    "$ROOT/.env.server.deps.example" \
    "${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/"
  rsync -avz "$ROOT/deploy/" "${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/deploy/"
  rsync -avz \
    "$ROOT/scripts/server-deps.sh" \
    "$ROOT/scripts/stack.sh" \
    "$ROOT/scripts/setup-stack-env.sh" \
    "$ROOT/scripts/setup-remote-dev-env.sh" \
    "$ROOT/scripts/verify-remote-deps.sh" \
    "$ROOT/scripts/lib/" \
    "${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/scripts/"
  rsync -avz "$ROOT/docs/zh/operations/server-deps.md" \
    "${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/README.md"
  remote_shell <<EOF
set -euo pipefail
cd '${DEPLOY_PATH}'
chmod +x scripts/*.sh
[[ -f .env ]] || cp .env.server.deps.example .env
EOF
  info "同步完成（使用说明: ${DEPLOY_PATH}/README.md）"
}

cmd_up() {
  info "远程启动依赖栈 ${DEPLOY_HOST}:${DEPLOY_PATH}"
  remote_shell <<'REMOTE'
set -euo pipefail
cd "${DEPLOY_PATH:-/root/qzb/lvye}"
[[ -f .env ]] || cp .env.server.deps.example .env
set -a
source .env
set +a
export EXPOSE_DEPS=1
mkdir -p "${DATA_ROOT:-./data}"

optional_services=()
if docker image inspect "${PDF2ZH_IMAGE:-zhitan-pdf2zh:3.9.3}" >/dev/null 2>&1; then
  optional_services+=(pdf2zh-api)
else
  echo "[server-deps] 跳过 pdf2zh-api（镜像不存在，请: bash scripts/server-deps.sh build-images）"
fi
if docker image inspect "${SPEECH_IMAGE:-zhitan-speech:3.9.3}" >/dev/null 2>&1; then
  optional_services+=(speech-api)
else
  echo "[server-deps] 跳过 speech-api（镜像不存在，请: bash scripts/server-deps.sh build-images）"
fi

bash scripts/stack.sh pull 2>/dev/null || true
bash scripts/stack.sh up --profile knowflow --profile speech \
  postgres redis minio \
  knowflow-mysql knowflow-infinity knowflow-gotenberg ragflow knowflow-backend \
  "${optional_services[@]}"

echo "等待健康检查 …"
for i in $(seq 1 72); do
  if docker compose -p "${COMPOSE_PROJECT_NAME:-lvye}" exec -T postgres pg_isready -U "${POSTGRES_USER:-platform}" >/dev/null 2>&1 \
    && curl -fsS "http://127.0.0.1:${REMOTE_RAGFLOW_PORT:-40007}/v1/system/config" 2>/dev/null | grep -q '"code":0'; then
    echo "[server-deps] 依赖栈就绪"
    bash scripts/stack.sh ps
    exit 0
  fi
  sleep 5
done
echo "[server-deps] 健康检查超时" >&2
bash scripts/stack.sh ps
bash scripts/stack.sh logs ragflow --tail 30 2>/dev/null || true
exit 1
REMOTE
}

cmd_down() {
  info "远程停止依赖栈（不停止 Dify docker 项目）"
  remote_shell <<'REMOTE'
set -euo pipefail
cd "${DEPLOY_PATH:-/root/qzb/lvye}"
[[ -f .env ]] && source .env
export EXPOSE_DEPS=1
bash scripts/stack.sh down
echo "[server-deps] 已停止依赖容器"
REMOTE
}

cmd_status() {
  remote_shell <<'REMOTE'
cd "${DEPLOY_PATH:-/root/qzb/lvye}"
echo "=== compose projects ==="
docker compose ls 2>/dev/null || true
echo "=== lvye ==="
docker ps -a --filter label=com.docker.compose.project=lvye --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
echo "=== dify (勿停) ==="
docker ps --filter label=com.docker.compose.project=docker --format 'table {{.Names}}\t{{.Status}}' | head -8
REMOTE
}

cmd_cleanup_local() {
  echo "[server-deps] 清理过时容器与镜像（保留 Dify 与 lvye 所需）"

  docker ps -a --filter "label=com.docker.compose.project=zhitanai" -q \
    | xargs -r docker rm -f 2>/dev/null || true

  local -a old_images=(
    zhitanai-worker:latest
    zhitanai-api:latest
    platform-speech-api:latest
    platform-worker:latest
    pdf-trans-frontend:prod
    byaidu/pdf2zh:latest
    elasticsearch:8.11.3
    docker.1ms.run/library/elasticsearch:8.11.3
  )
  local img
  for img in "${old_images[@]}"; do
    docker rmi -f "$img" 2>/dev/null || true
  done

  docker image prune -f 2>/dev/null || true
  docker builder prune -af 2>/dev/null || true

  echo "[server-deps] 清理完成"
  docker system df
}

cmd_cleanup() {
  info "远程清理 ${DEPLOY_HOST}:${DEPLOY_PATH}"
  remote_shell <<'REMOTE'
set -euo pipefail
cd "${DEPLOY_PATH:-/root/qzb/lvye}"
bash scripts/server-deps.sh cleanup-local
REMOTE
}

usage() {
  cat <<EOF
用法: bash scripts/server-deps.sh <sync|push-images|up|down|status|cleanup|cleanup-local>

  sync           同步编排/脚本到 ${DEPLOY_PATH}
  rebuild-amd64  服务器上用 stack.sh 重建 amd64 镜像
  build-images   在 amd64 服务器上构建 pdf2zh / speech 镜像
  push-images    本机导入镜像（仅同架构可用）
  up             启动远程依赖（EXPOSE_DEPS=1，Infinity 向量库）
  down           停止远程依赖（不影响 Dify）
  status         查看远程状态
  cleanup        远程清理过时 zhitanAI 容器与 ES 等镜像

环境: DEPLOY_HOST=${DEPLOY_HOST} DEPLOY_PATH=${DEPLOY_PATH}
编排: scripts/stack.sh + compose.expose-deps.yaml
EOF
}

main() {
  case "${1:-}" in
    sync) cmd_sync ;;
    rebuild-amd64) cmd_rebuild_amd64 ;;
    build-images) cmd_sync; cmd_build_images ;;
    push-images) cmd_push_images ;;
    up) cmd_sync; cmd_up ;;
    down) cmd_down ;;
    status) cmd_status ;;
    cleanup) cmd_sync; cmd_cleanup ;;
    cleanup-local) cmd_cleanup_local ;;
    -h|--help|help|"") usage ;;
    *) error "未知命令: $1"; usage; exit 1 ;;
  esac
}

main "$@"
