#!/usr/bin/env bash
# 快速同步本机代码到服务器并生效（共用远程 Postgres/Redis/MinIO 与容器依赖）
#
# 服务器需 SERVER_MOUNT_CODE=1（stack.sh server-up）：挂载 backend/app，同步后自动重启容器
#
# 用法:
#   ./dev.sh sync                  # 同步后端 + 重启 API / Worker
#   ./dev.sh sync --frontend       # 同步前端源码 + npm build + nginx reload（挂载 dist，不重建镜像）
#   ./dev.sh sync --all            # 后端 + 前端
#   ./dev.sh sync --browser            # 同步后在服务器重建 Playwright runtime
#
# 配置: backend/deploy.target（可选，默认 172.19.134.45:/root/qzb/lvye）
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="$ROOT/backend"

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
  remote "mkdir -p '${DEPLOY_PATH}/backend/app' '${DEPLOY_PATH}/backend/workers' '${DEPLOY_PATH}/examples/agent-skills' '${DEPLOY_PATH}/docs' '${DEPLOY_PATH}/scripts/lib'"
  rsync "${RSYNC_OPTS[@]}" \
    --exclude '__pycache__/' --exclude '*.pyc' \
    "$ROOT/backend/app/" "${dest}backend/app/"
  rsync "${RSYNC_OPTS[@]}" \
    --exclude '__pycache__/' \
    "$ROOT/backend/workers/" "${dest}backend/workers/"
  rsync -avz \
    "$ROOT/examples/agent-skills/" "${dest}examples/agent-skills/"
  rsync -avz \
    "$ROOT/docs/" "${dest}docs/" \
    "$ROOT/RELEASE.md" "${dest}RELEASE.md" \
    "$ROOT/运维部署指南.md" "${dest}运维部署指南.md" 2>/dev/null || true
  rsync -avz \
    "$ROOT/compose.yaml" "${dest}compose.yaml" \
    "$ROOT/compose.server.yaml" "${dest}compose.server.yaml" \
    "$ROOT/.env.stack.example" "${dest}.env.stack.example" \
    "$ROOT/scripts/stack.sh" "${dest}scripts/stack.sh" \
    "$ROOT/scripts/setup-stack-env.sh" "${dest}scripts/setup-stack-env.sh" \
    "$ROOT/scripts/setup-browser-rpa.sh" "${dest}scripts/setup-browser-rpa.sh" \
    "$ROOT/scripts/lib/browser-rpa.sh" "${dest}scripts/lib/browser-rpa.sh" \
    "$ROOT/backend/Dockerfile" "${dest}backend/Dockerfile" \
    "$ROOT/backend/pyproject.toml" "${dest}backend/pyproject.toml" \
    2>/dev/null || true

  if [[ "$SYNC_FRONTEND" == 1 ]]; then
    info "同步前端 → ${dest}"
    rsync "${RSYNC_OPTS[@]}" \
      --exclude 'node_modules/' --exclude 'dist/' \
      "$ROOT/frontend/" "${dest}frontend/"
    rsync -avz "$ROOT/frontend/nginx.conf" "${dest}frontend/nginx.conf"
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
[[ -f .env ]] && set -a && source .env && set +a
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
    echo "[sync] 警告: API 未在 60s 内就绪，尝试 force-recreate api 容器…"
    SERVER_MOUNT_CODE=1 COMPOSE_PROJECT_NAME="\${proj}" bash scripts/stack.sh server-up -d --force-recreate api 2>/dev/null || true
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
  compose_stamp=".sync-compose-server.sha256"
  compose_changed=0
  compose_hash=""
  if [[ -f compose.server.yaml ]]; then
    compose_hash="\$(sha256sum compose.server.yaml | awk '{print \$1}')"
    old_hash="\$(cat "\${compose_stamp}" 2>/dev/null || true)"
    [[ "\${compose_hash}" != "\${old_hash}" ]] && compose_changed=1
  fi
  if [[ "\${compose_changed}" == 1 ]]; then
    echo "[sync] compose.server.yaml 已变更，compose up API / Worker…"
  else
    echo "[sync] 同步挂载代码，重启 API / Worker（6 worker + Celery 12，跳过 force-recreate）…"
  fi
  if [[ ! -f .env ]]; then
    bash scripts/setup-stack-env.sh 2>/dev/null || cp -f .env.stack.example .env
  fi
  pg_cid="\$(docker ps -q -f "name=\${proj}-postgres" | head -1)"
  if [[ -n "\$pg_cid" ]]; then
    pg_max="\$(docker exec "\$pg_cid" psql -U "\${POSTGRES_USER:-platform}" -tAc "SHOW max_connections;" 2>/dev/null | tr -d '[:space:]' || true)"
    if [[ "\${pg_max}" != "220" ]]; then
      echo "[sync] Postgres max_connections=\${pg_max:-?} → 应用 220（重建 postgres 容器，数据卷保留）…"
      SERVER_MOUNT_CODE=1 COMPOSE_PROJECT_NAME="\${proj}" bash scripts/stack.sh server-up -d --force-recreate postgres
    fi
  fi
  api_cid="\$(docker ps -q -f "name=\${proj}-api" | head -1)"
  worker_cid="\$(docker ps -q -f "name=\${proj}-worker" | head -1)"
  if [[ "\${compose_changed}" == 1 || -z "\${api_cid}" ]]; then
    SERVER_MOUNT_CODE=1 COMPOSE_PROJECT_NAME="\${proj}" bash scripts/stack.sh server-up -d api worker
    [[ -n "\${compose_hash}" ]] && echo "\${compose_hash}" > "\${compose_stamp}"
  else
    restart_ids=""
    [[ -n "\${api_cid}" ]] && restart_ids="\${api_cid}"
    [[ -n "\${worker_cid}" ]] && restart_ids="\${restart_ids} \${worker_cid}"
    if [[ -n "\${restart_ids}" ]]; then
      # shellcheck disable=SC2086
      docker restart \${restart_ids}
    else
      SERVER_MOUNT_CODE=1 COMPOSE_PROJECT_NAME="\${proj}" bash scripts/stack.sh server-up -d api worker
      [[ -n "\${compose_hash}" ]] && echo "\${compose_hash}" > "\${compose_stamp}"
    fi
  fi
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
  cd frontend
  node_image="\${NODE_IMAGE:-node:22-alpine}"
  npm_registry="\${NPM_REGISTRY:-https://registry.npmmirror.com}"
  lock_stamp=".node_modules-lock.sha256"
  need_npm=1
  if [[ -x node_modules/.bin/vite && -f "\${lock_stamp}" && -f package-lock.json ]]; then
    current="\$(sha256sum package-lock.json | awk '{print \$1}')"
    saved="\$(cat "\${lock_stamp}" 2>/dev/null || true)"
    [[ "\${current}" == "\${saved}" ]] && need_npm=0
  fi
  fe_install_and_build='npm ci --prefer-offline 2>/dev/null || npm install; VITE_API_BASE=/ai VITE_BASE_PATH=/ai/ npm run build'
  if [[ "\${need_npm}" == 1 ]]; then
    echo "[sync] 安装/更新前端依赖（package-lock.json 已变更或 node_modules 未就绪）…"
    if command -v npm >/dev/null 2>&1; then
      sh -c "\${fe_install_and_build}"
    else
      docker run --rm \
        -v "\$(pwd):/app" -w /app \
        -e NPM_CONFIG_REGISTRY="\${npm_registry}" \
        -e VITE_API_BASE=/ai \
        -e VITE_BASE_PATH=/ai/ \
        "\${node_image}" \
        sh -c "\${fe_install_and_build}"
    fi
    sha256sum package-lock.json | awk '{print \$1}' > "\${lock_stamp}"
  else
    VITE_API_BASE=/ai VITE_BASE_PATH=/ai/ npm run build
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
    error "请配置 DEPLOY_HOST / DEPLOY_PATH（backend/deploy.target）"
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
