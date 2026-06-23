#!/usr/bin/env bash
# 快速同步本机代码到服务器并生效（共用远程 Postgres/Redis/MinIO 与容器依赖）
#
# 服务器需 SERVER_MOUNT_CODE=1（stack.sh server-up）：挂载 platform/app，同步后自动重启容器
#
# 用法:
#   ./dev.sh sync                  # 同步后端 + 重启 API / Worker
#   ./dev.sh sync --frontend       # 同步前端源码 + npm build + nginx reload（挂载 dist，不重建镜像）
#   ./dev.sh sync --all            # 后端 + 前端
#   ./dev.sh sync --browser            # 同步后在服务器重建 Playwright runtime
#
# 配置: platform/deploy.target（可选，默认 172.19.134.45:/root/qzb/lvye）
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="$ROOT/platform"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
info()  { echo -e "${GREEN}[sync]${NC} $*"; }
warn()  { echo -e "${YELLOW}[sync]${NC} $*"; }
error() { echo -e "${RED}[sync]${NC} $*" >&2; }

DEPLOY_USER="${DEPLOY_USER:-root}"
DEPLOY_HOST="${DEPLOY_HOST:-172.19.134.45}"
DEPLOY_PATH="${DEPLOY_PATH:-/root/qzb/lvye}"

SYNC_FRONTEND=0
RESTART_API=1
SYNC_BROWSER=0
RSYNC_OPTS=(-avz --delete)

load_target() {
  local f="$PLATFORM/deploy.target"
  [[ -f "$f" ]] || return 0
  # shellcheck disable=SC1090
  set -a && source "$f" && set +a
  DEPLOY_USER="${DEPLOY_USER:-root}"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --frontend) SYNC_FRONTEND=1; shift ;;
      --all) SYNC_FRONTEND=1; shift ;;
      --no-restart-api) RESTART_API=0; shift ;;
      --browser) SYNC_BROWSER=1; shift ;;
      --restart-api)
        warn "--restart-api 已废弃（默认即重启 API），请直接使用 ./dev.sh sync"
        shift
        ;;
      -h|--help)
        sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
        exit 0
        ;;
      *) error "未知参数: $1"; exit 1 ;;
    esac
  done
}

remote() {
  ssh -o BatchMode=yes -o ConnectTimeout=15 "${DEPLOY_USER}@${DEPLOY_HOST}" "$@"
}

rsync_to_server() {
  local dest="${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/"
  info "同步后端 → ${dest}"
  remote "mkdir -p '${DEPLOY_PATH}/platform/app' '${DEPLOY_PATH}/platform/workers' '${DEPLOY_PATH}/docs' '${DEPLOY_PATH}/scripts/lib'"
  rsync "${RSYNC_OPTS[@]}" \
    --exclude '__pycache__/' --exclude '*.pyc' \
    "$ROOT/platform/app/" "${dest}platform/app/"
  rsync "${RSYNC_OPTS[@]}" \
    --exclude '__pycache__/' \
    "$ROOT/platform/workers/" "${dest}platform/workers/"
  rsync -avz \
    "$ROOT/docs/" "${dest}docs/" \
    "$ROOT/RELEASE.md" "${dest}RELEASE.md" \
    "$ROOT/运维部署指南.md" "${dest}运维部署指南.md" 2>/dev/null || true
  rsync -avz \
    "$ROOT/compose.yaml" "${dest}compose.yaml" \
    "$ROOT/compose.server.yaml" "${dest}compose.server.yaml" \
    "$ROOT/scripts/stack.sh" "${dest}scripts/stack.sh" \
    "$ROOT/scripts/setup-browser-rpa.sh" "${dest}scripts/setup-browser-rpa.sh" \
    "$ROOT/scripts/lib/browser-rpa.sh" "${dest}scripts/lib/browser-rpa.sh" \
    "$ROOT/platform/Dockerfile" "${dest}platform/Dockerfile" \
    "$ROOT/platform/pyproject.toml" "${dest}platform/pyproject.toml" \
    2>/dev/null || true

  if [[ "$SYNC_FRONTEND" == 1 ]]; then
    info "同步前端 → ${dest}"
    rsync "${RSYNC_OPTS[@]}" \
      --exclude 'node_modules/' --exclude 'dist/' \
      "$ROOT/platform-frontend/" "${dest}platform-frontend/"
    rsync -avz "$ROOT/platform-frontend/nginx.conf" "${dest}platform-frontend/nginx.conf"
    rsync -avz "$ROOT/compose.server.yaml" "${dest}compose.server.yaml"
  fi
}

apply_on_server() {
  local fe_flag="$1"
  local api_flag="$2"
  info "服务器生效（${DEPLOY_HOST}）…"
  remote bash -s <<EOF
set -euo pipefail
cd '${DEPLOY_PATH}'
proj="\${COMPOSE_PROJECT_NAME:-lvye}"

wait_api_ready() {
  echo "[sync] 等待 API 就绪…"
  local ok=0
  for i in \$(seq 1 30); do
    if curl -sf -o /dev/null --max-time 5 http://127.0.0.1:40005/ai/api/v1/system/client-config 2>/dev/null; then
      echo "[sync] API 已就绪（client-config OK）"
      ok=1
      break
    fi
    sleep 2
  done
  if [[ "\$ok" != 1 ]]; then
    echo "[sync] 警告: API 未在 60s 内就绪，尝试强制重建 api 容器…"
    SERVER_MOUNT_CODE=1 COMPOSE_PROJECT_NAME="\${proj}" bash scripts/stack.sh server-up api 2>/dev/null || true
    for i in \$(seq 1 15); do
      if curl -sf -o /dev/null --max-time 5 http://127.0.0.1:40005/ai/api/v1/system/client-config 2>/dev/null; then
        echo "[sync] API 已就绪（重试成功）"
        ok=1
        break
      fi
      sleep 2
    done
  fi
  [[ "\$ok" == 1 ]] || echo "[sync] 警告: API 仍不可用，请 ssh 检查 lvye-api-1 日志"
}

if [[ "${api_flag}" == 1 ]]; then
  echo "[sync] 重建 API / Worker（compose up -d + restart，加载挂载的新代码）…"
  SERVER_MOUNT_CODE=1 COMPOSE_PROJECT_NAME="\${proj}" bash scripts/stack.sh server-up api worker
  # compose up -d 在配置未变时不会重启已运行容器，uvicorn 多 worker 会继续用旧内存代码
  for svc in api worker; do
    cid="\$(docker ps -q -f "name=\${proj}-\${svc}")"
    if [[ -n "\$cid" ]]; then
      docker restart \$cid
      echo "[sync] restarted \${proj}-\${svc}"
    fi
  done
  wait_api_ready
else
  echo "[sync] 跳过 API 重建（--no-restart-api）"
  restart_by_name() {
    local pattern="\$1"
    local cid
    cid="\$(docker ps -q -f "name=\${pattern}")"
    if [[ -n "\$cid" ]]; then
      docker restart \$cid
      echo "[sync] restarted \${pattern}"
    fi
  }
  restart_by_name "\${proj}-worker"
fi

# 浏览器 RPA：api 就绪后自动检测，缺失则重建 Playwright runtime
if [[ "${api_flag}" == 1 ]]; then
  export INSTALL_BROWSER=1
  export SERVER_MOUNT_CODE=1
  if ! docker exec "\$(docker ps -q -f name=\${proj}-api | head -1)" python -c \
    "from playwright.sync_api import sync_playwright" 2>/dev/null; then
    echo "[sync] 自动构建 Playwright runtime（Docker，约 3–8 分钟）…"
    bash scripts/stack.sh build-browser
  fi
fi

if [[ "${fe_flag}" == 1 ]]; then
  echo "[sync] 构建前端静态资源（挂载 dist，不重建 zhitan-frontend 镜像）…"
  cd platform-frontend
  node_image="\${NODE_IMAGE:-node:22-alpine}"
  npm_registry="\${NPM_REGISTRY:-https://registry.npmmirror.com}"
  if [[ -x node_modules/.bin/vite ]]; then
    VITE_API_BASE=/ai VITE_BASE_PATH=/ai/ npm run build
  else
    docker run --rm \
      -v "\$(pwd):/app" -w /app \
      -e NPM_CONFIG_REGISTRY="\${npm_registry}" \
      -e VITE_API_BASE=/ai \
      -e VITE_BASE_PATH=/ai/ \
      "\${node_image}" \
      sh -c 'npm ci --prefer-offline 2>/dev/null || npm install && npm run build'
  fi
  cd ..
  fe_cid=\$(docker ps -q -f "name=\${proj}-frontend")
  if [[ -n "\$fe_cid" ]]; then
    if docker exec "\$fe_cid" nginx -s reload 2>/dev/null; then
      echo "[sync] nginx reload 完成（dist / nginx.conf 已挂载进容器）"
    else
      echo "[sync] nginx reload 失败，尝试重启 frontend…"
      docker restart "\$fe_cid"
    fi
  else
    echo "[sync] 未找到 frontend 容器，请执行: bash scripts/stack.sh server-up"
  fi
fi

echo "[sync] 校验…"
curl -sf -o /dev/null -w "  服务器 Web /ai/: HTTP %{http_code}\n" http://127.0.0.1:40005/ai/ || true
curl -sf http://127.0.0.1:40005/ai/api/v1/system/version && echo || true
EOF
}

main() {
  parse_args "$@"
  load_target
  [[ -n "${DEPLOY_HOST}" && -n "${DEPLOY_PATH}" ]] || {
    error "请配置 DEPLOY_HOST / DEPLOY_PATH（platform/deploy.target）"
    exit 1
  }
  info "目标: ${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}"
  remote "echo ok" >/dev/null || { error "SSH 连接失败"; exit 1; }
  rsync_to_server
  apply_on_server "$SYNC_FRONTEND" "$RESTART_API"
  if [[ "$SYNC_BROWSER" == 1 && "$RESTART_API" != 1 ]]; then
    info "强制重建 Playwright runtime…"
    remote bash -s <<EOF
set -euo pipefail
cd '${DEPLOY_PATH}'
export INSTALL_BROWSER=1 SERVER_MOUNT_CODE=1
export COMPOSE_PROJECT_NAME="\${COMPOSE_PROJECT_NAME:-lvye}"
[[ -f .env ]] && set -a && source .env && set +a
bash scripts/stack.sh build-browser
EOF
  fi
  info "完成。本机开发: ./dev.sh local  |  服务器 Web: http://${DEPLOY_HOST}:40005/ai/"
}

main "$@"
