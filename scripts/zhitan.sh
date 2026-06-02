#!/usr/bin/env bash
# 智碳平台 — 本地开发与运维统一入口（配置见 platform/.env.example、deploy.target.example）
#
#   bash scripts/zhitan.sh              # 启动（同 start）
#   bash scripts/zhitan.sh stop         # 停止
#   bash scripts/zhitan.sh env          # 修正本地 .env 误用远程地址
#   bash scripts/zhitan.sh knowflow setup|build
#   bash scripts/zhitan.sh deploy …     # 转 deploy.sh（远程部署）
# - 有 .venv / node_modules 时：pdf2zh、平台 API、Worker、前端在宿主机运行
# - 无本地环境时：回退 Docker 构建 api/worker/frontend
# - 基础设施（postgres / redis / minio）默认 Docker
set -euo pipefail
# 避免上次 KnowFlow amd64 构建遗留的全局平台变量影响平台基础设施
unset DOCKER_DEFAULT_PLATFORM DOCKER_PLATFORM

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM="$ROOT/platform"
FRONTEND="$ROOT/platform-frontend"
RUN_DIR="$ROOT/.run"
LOG_DIR="$RUN_DIR/logs"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.local.yml"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[start]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $*"; }
error() { echo -e "${RED}[error]${NC} $*" >&2; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { error "未找到命令: $1"; exit 1; }
}

wait_url() {
  local url="$1" label="$2" retries="${3:-30}" interval="${4:-2}"
  local i
  for i in $(seq 1 "$retries"); do
    if curl -sf "$url" >/dev/null 2>&1; then
      info "$label 就绪"
      return 0
    fi
    sleep "$interval"
  done
  return 1
}

start_bg() {
  local name="$1" pid_file="$2" log_file="$3"
  shift 3
  mkdir -p "$(dirname "$pid_file")" "$LOG_DIR"
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    info "$name 已在运行 (PID $(cat "$pid_file"))"
    return 0
  fi
  info "启动 $name ..."
  nohup "$@" >"$log_file" 2>&1 &
  echo $! >"$pid_file"
}

# --- 本地环境探测 ---

has_pdf2zh_local() {
  [[ -x "$ROOT/.venv/bin/pdf2zh_next" ]] || command -v pdf2zh_next >/dev/null 2>&1
}

pdf2zh_bin() {
  if [[ -x "$ROOT/.venv/bin/pdf2zh_next" ]]; then
    echo "$ROOT/.venv/bin/pdf2zh_next"
  else
    command -v pdf2zh_next
  fi
}

has_platform_venv() {
  [[ -x "$PLATFORM/.venv/bin/uvicorn" && -x "$PLATFORM/.venv/bin/celery" ]]
}

has_frontend_local() {
  [[ -d "$FRONTEND/node_modules" ]] && command -v npm >/dev/null 2>&1
}

# --- 各组件启动 ---

start_pdf2zh_api() {
  local bin
  bin="$(pdf2zh_bin)" || {
    error "未找到 pdf2zh_next。请在仓库根目录执行: pip install -e ."
    exit 1
  }
  if curl -sf "http://127.0.0.1:7861/api/health" >/dev/null 2>&1; then
    info "pdf2zh API 已在 7861 端口监听"
    return 0
  fi
  start_bg "pdf2zh API" "$RUN_DIR/pdf2zh-api.pid" "$LOG_DIR/pdf2zh-api.log" \
    "$bin" --api --api-port 7861
  wait_url "http://127.0.0.1:7861/api/health" "pdf2zh API" 60 2 \
    || { error "pdf2zh API 启动超时，日志: $LOG_DIR/pdf2zh-api.log"; exit 1; }
}

start_infra_docker() {
  require_cmd docker
  cd "$PLATFORM"
  [[ -f .env ]] || { info "复制 .env.example → .env"; cp .env.example .env; }
  info "启动 Docker 基础设施 (postgres, redis, minio) ..."
  $COMPOSE up -d postgres redis minio
  wait_url "http://127.0.0.1:9000/minio/health/live" "MinIO" 20 2 || true
}

start_speech_stack() {
  require_cmd docker
  SPEECH_MODELS="${SPEECH_MODELS_DIR:-$ROOT/.run/speech-models}"
  mkdir -p "$SPEECH_MODELS"
  export SPEECH_MODELS_DIR="$SPEECH_MODELS"
  cd "$PLATFORM"
  if ! curl -sf "http://127.0.0.1:8765/health" >/dev/null 2>&1; then
    if [[ ! -f docker-compose.speech.yml ]]; then
      warn "未找到 docker-compose.speech.yml，跳过语音栈"
      return 0
    fi
    info "启动本地语音转写栈 (speech-api)，模型目录: $SPEECH_MODELS ..."
    docker compose -f docker-compose.speech.yml up -d
    warn "首次启动会下载 FunASR 模型（ModelScope），约需数分钟"
    wait_url "http://127.0.0.1:8765/health" "speech-api" 90 5 \
      || warn "speech-api 可能仍在初始化，日志: docker compose -f docker-compose.speech.yml logs speech-api"
  else
    info "speech-api 已在 8765 端口监听"
  fi
}

ensure_speech_service() {
  if curl -sf "http://127.0.0.1:8765/health" >/dev/null 2>&1; then
    info "speech-api 已在 8765 端口监听"
    return 0
  fi
  if [[ -x "$ROOT/platform/speech-service/.venv/bin/uvicorn" ]]; then
    info "启动宿主机 speech-api（会议助手）..."
    bash "$ROOT/scripts/start_speech_local.sh" || warn "speech-api 启动失败"
    wait_url "http://127.0.0.1:8765/health" "speech-api" 60 5 \
      || warn "speech-api 可能仍在加载模型，日志: $ROOT/.run/logs/speech-api.log"
    return 0
  fi
  if command -v docker >/dev/null 2>&1 && [[ -f "$PLATFORM/docker-compose.speech.yml" ]]; then
    start_speech_stack
  else
    warn "未检测到语音服务，会议助手不可用。可执行: bash scripts/setup_speech.sh"
  fi
}

start_knowflow_stack() {
  require_cmd docker
  if [[ ! -d "$PLATFORM/third_party/KnowFlow" ]]; then
    info "首次使用 KnowFlow，正在克隆源码 ..."
    zhitan_knowflow_setup
  fi
  [[ -f "$PLATFORM/knowflow.env" ]] || cp "$PLATFORM/knowflow.env.example" "$PLATFORM/knowflow.env"
  cd "$PLATFORM"
  set -a
  # shellcheck disable=SC1091
  source knowflow.env
  set +a
  export COMPOSE_PROFILES="${COMPOSE_PROFILES:-elasticsearch}"
  local -a kf_profile_args=()
  local p
  IFS=',' read -ra _kf_prof <<< "${COMPOSE_PROFILES}"
  for p in "${_kf_prof[@]}"; do
    p="${p// /}"
    [[ -n "$p" ]] && kf_profile_args+=(--profile "$p")
  done
  if ! docker image inspect knowflow-ragflow:source >/dev/null 2>&1 \
    || ! docker image inspect knowflow-server:source >/dev/null 2>&1; then
    error "缺少源码镜像，请先执行: bash scripts/zhitan.sh knowflow build"
    exit 1
  fi
  info "启动 KnowFlow 栈（docker-compose.knowflow.yml，arm64 源码镜像）..."
  docker compose -p knowflow "${kf_profile_args[@]}" -f docker-compose.knowflow.yml --env-file knowflow.env up -d --force-recreate ragflow knowflow-backend
  warn "等待 RAGFlow 就绪（约 2–5 分钟，首次启动更久）..."
  wait_url "http://127.0.0.1:9380" "RAGFlow" 90 5 || warn "RAGFlow 可能仍在初始化"
  local kf_port=5001
  grep -q '^KNOWFLOW_BACKEND_PORT=' knowflow.env 2>/dev/null && kf_port=$(grep '^KNOWFLOW_BACKEND_PORT=' knowflow.env | cut -d= -f2)
  wait_url "http://127.0.0.1:${kf_port}/health" "KnowFlow Backend" 60 3 || true
  if [[ -f "$PLATFORM/.env" ]]; then
    # 保证末行有换行，避免 >> 拼到上一行
    [[ -z $(tail -c1 "$PLATFORM/.env" 2>/dev/null | tr -d '\n') ]] || echo >> "$PLATFORM/.env"
    ensure_env_kv() {
      local key="$1" val="$2"
      grep -q "^${key}=" "$PLATFORM/.env" || printf '%s=%s\n' "$key" "$val" >> "$PLATFORM/.env"
    }
    ensure_env_kv KNOWFLOW_ENABLED true
    ensure_env_kv KNOWFLOW_UI_PROXY_PREFIX /ragflow-ui
    ensure_env_kv DESIGN_SYSTEM_PROXY_PREFIX /design-system-ui
    ensure_env_kv SMART_FORECAST_PROXY_PREFIX /smart-forecast-ui
    ensure_env_kv RAGFLOW_ACCOUNT_MODE shared
    ensure_env_kv RAGFLOW_SHARED_EMAIL admin@gmail.com
    ensure_env_kv RAGFLOW_SHARED_PASSWORD admin
    ensure_env_kv SMART_DATA_QUERY_V2_DIFY_BASE_URL "http://172.19.134.45:40001/v1"
    ensure_env_kv SMART_DATA_QUERY_V2_DIFY_API_KEY "app-61GFhU5Lw1nESxMXv7mmuSzR"
    info "KnowFlow 集成已写入 platform/.env（默认 RAGFLOW_ACCOUNT_MODE=shared，可按需改为 mapped）"
  fi
}

ensure_smart_data_query_v2_env() {
  [[ -f "$PLATFORM/.env" ]] || return 0
  [[ -z $(tail -c1 "$PLATFORM/.env" 2>/dev/null | tr -d '\n') ]] || echo >> "$PLATFORM/.env"
  ensure_env_kv() {
    local key="$1" val="$2"
    grep -q "^${key}=" "$PLATFORM/.env" || printf '%s=%s\n' "$key" "$val" >> "$PLATFORM/.env"
  }
  ensure_env_kv SMART_DATA_QUERY_V2_DIFY_BASE_URL "http://172.19.134.45:40001/v1"
  ensure_env_kv SMART_DATA_QUERY_V2_DIFY_API_KEY "app-61GFhU5Lw1nESxMXv7mmuSzR"
  ensure_env_kv CARBON_QA_V2_CHAT_BASE_URL "http://172.19.134.45:40001/v1"
  ensure_env_kv CARBON_QA_V2_CHAT_API_KEY "app-eTtTSHqC9w2Di8CHVUVLu98s"
}

restart_platform_api_local() {
  local pid_file="$RUN_DIR/platform-api.pid"
  pkill -f "uvicorn app.main:app --reload --host 127.0.0.1 --port 8000" 2>/dev/null || true
  if [[ -f "$pid_file" ]]; then
    kill "$(cat "$pid_file")" 2>/dev/null || true
    pkill -P "$(cat "$pid_file")" 2>/dev/null || true
    rm -f "$pid_file"
  fi
  sleep 1
}

start_platform_api_local() {
  ensure_smart_data_query_v2_env
  if curl -sf "http://127.0.0.1:8000/docs" >/dev/null 2>&1; then
    info "平台 API 已在 8000 端口监听"
    return 0
  fi
  local pid_file="$RUN_DIR/platform-api.pid"
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    warn "平台 API 进程存在但未响应（可能启动时数据库未就绪），正在重启 ..."
    kill "$(cat "$pid_file")" 2>/dev/null || true
    pkill -P "$(cat "$pid_file")" 2>/dev/null || true
    rm -f "$pid_file"
  fi
  start_bg "平台 API" "$RUN_DIR/platform-api.pid" "$LOG_DIR/platform-api.log" \
    bash -c "cd '$PLATFORM' && source .venv/bin/activate && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
  wait_url "http://127.0.0.1:8000/docs" "平台 API" 30 2 \
    || warn "平台 API 可能仍在启动，日志: $LOG_DIR/platform-api.log"
}

start_platform_worker_local() {
  start_bg "Celery Worker" "$RUN_DIR/platform-worker.pid" "$LOG_DIR/platform-worker.log" \
    bash -c "cd '$PLATFORM' && source .venv/bin/activate && celery -A workers.celery_app worker --loglevel=info"
}

start_frontend_local() {
  if curl -sf "http://127.0.0.1:40005/ai/" >/dev/null 2>&1; then
    info "平台前端已在 40005 端口监听"
    return 0
  fi
  start_bg "平台前端" "$RUN_DIR/platform-frontend.pid" "$LOG_DIR/platform-frontend.log" \
    bash -c "cd '$FRONTEND' && npm run dev -- --host 127.0.0.1 --port 40005"
  wait_url "http://127.0.0.1:40005/ai/" "平台前端" 30 2 \
    || warn "平台前端可能仍在启动，日志: $LOG_DIR/platform-frontend.log"
}

start_platform_docker() {
  require_cmd docker
  cd "$PLATFORM"
  [[ -f .env ]] || { info "复制 .env.example → .env"; cp .env.example .env; }
  info "本地无 platform/.venv，使用 Docker 构建 api / worker / frontend ..."
  $COMPOSE --profile docker-app up -d --build api worker frontend
  wait_url "http://127.0.0.1:8000/docs" "平台 API" 30 2 \
    || warn "平台 API 可能仍在启动"
}

mode_speech() {
  info "模式: 本地优先 + 语音栈 (speech)"
  start_infra_docker
  start_speech_stack
  mode_local
  print_urls speech
}

mode_local() {
  info "模式: 本地优先 (local)"
  zhitan_fix_local_env
  start_infra_docker
  if has_pdf2zh_local; then
    start_pdf2zh_api
  else
    warn "未找到 pdf2zh 本地环境，跳过 pdf2zh API（翻译功能不可用）"
  fi
  if has_platform_venv; then
    start_platform_api_local
    start_platform_worker_local
  else
    warn "未找到 platform/.venv，回退 Docker 运行平台后端"
    start_platform_docker
    print_urls
    return
  fi
  if has_frontend_local; then
    start_frontend_local
  else
    warn "未找到 platform-frontend/node_modules，回退 Docker 前端"
    cd "$PLATFORM"
    $COMPOSE --profile docker-app up -d frontend
  fi
  ensure_speech_service
}

mode_docker() {
  info "模式: Docker 混合 (docker) — 宿主机 pdf2zh + Docker 平台"
  start_infra_docker
  if has_pdf2zh_local; then
    start_pdf2zh_api
  else
    error "docker 模式需要本地 pdf2zh_next (pip install -e .)"
    exit 1
  fi
  cd "$PLATFORM"
  $COMPOSE --profile docker-app up -d --build api worker frontend
  wait_url "http://127.0.0.1:8000/docs" "平台 API" 30 2 || true
  print_urls
}

mode_docker_full() {
  info "模式: 全 Docker (docker-full)"
  require_cmd docker
  cd "$PLATFORM"
  [[ -f .env ]] || cp .env.example .env
  docker compose --profile docker-full up -d --build
  print_urls
}

mode_knowflow() {
  info "模式: 本地优先 + KnowFlow 知识库栈"
  start_infra_docker
  start_knowflow_stack
  mode_local
  print_urls knowflow
  return
}

print_urls() {
  local with_knowflow="${1:-}"
  cat <<EOF

${GREEN}=== 智碳平台 AI 系统已启动 ===${NC}

  平台前端:     http://127.0.0.1:40005/ai/  → 系统功能 → 知识问答（内嵌 KnowFlow 完整界面）
  平台 API:     http://127.0.0.1:8000  (Swagger: /docs)
  pdf2zh API:   http://127.0.0.1:7861
  MinIO 控制台: http://127.0.0.1:9001  (minioadmin / minioadmin)
EOF
  if [[ "$with_knowflow" == *knowflow* ]]; then
    cat <<EOF
  RAGFlow:      http://127.0.0.1:9380
  KnowFlow API: http://127.0.0.1:5001
EOF
  fi
  if [[ "$with_knowflow" == *speech* ]]; then
    cat <<EOF
  语音转写 API: http://127.0.0.1:8765  （总结走 DeepSeek 在线 API）
EOF
  fi
  cat <<EOF

  默认账号: admin / admin123

  停止: bash scripts/zhitan.sh stop
  日志: ls $LOG_DIR/

EOF
}

zhitan_fix_local_env() {
  # 原 ensure_local_env.sh
  local ENV_FILE="$PLATFORM/.env" KF_FILE="$PLATFORM/knowflow.env"
  local LOCAL_ENV_EXAMPLE="$PLATFORM/.env.example"
  local LOCAL_KF_EXAMPLE="$PLATFORM/knowflow.env.example"
  sed_inplace() {
    if sed --version 2>/dev/null | grep -q GNU; then sed -i "$@"; else sed -i '' "$@"; fi
  }
  needs_local_fix() {
    [[ -f "$ENV_FILE" ]] || return 1
    grep -qE '@postgres:|@postgres/|redis://redis:|^MINIO_ENDPOINT=minio:|^SPEECH_SERVICE_URL=http://speech-api:|^KNOWFLOW_BACKEND_URL=http://knowflow-backend:|^RAGFLOW_API_URL=http://ragflow-server:|^KNOWFLOW_UI_URL=http://172\.|^RAGFLOW_API_URL=http://172\.|^KNOWFLOW_BACKEND_URL=http://172\.|^SPEECH_SERVICE_URL=http://172\.|^DEPLOY_HOST=|^FRONTEND_PORT=' \
      "$ENV_FILE"
  }
  if [[ ! -f "$ENV_FILE" ]]; then
    [[ -f "$LOCAL_ENV_EXAMPLE" ]] && cp "$LOCAL_ENV_EXAMPLE" "$ENV_FILE" && info "已创建 platform/.env"
  elif needs_local_fix; then
    warn "platform/.env 含远程/Docker 地址，改回本机开发…"
    local tmp; tmp="$(mktemp)"; cp "$ENV_FILE" "$tmp"
    sed_inplace \
      -e 's|@postgres:5432|@127.0.0.1:5433|g' -e 's|@postgres/|@127.0.0.1:5433/|g' \
      -e 's|^REDIS_URL=redis://redis:|REDIS_URL=redis://127.0.0.1:|g' \
      -e 's|^MINIO_ENDPOINT=minio:9000|MINIO_ENDPOINT=127.0.0.1:9000|' \
      -e 's|^PDF2ZH_API_URL=http://pdf2zh-api:7861|PDF2ZH_API_URL=http://127.0.0.1:7861|' \
      -e 's|^SPEECH_SERVICE_URL=http://speech-api:8765|SPEECH_SERVICE_URL=http://127.0.0.1:8765|' \
      -e 's|^SPEECH_SERVICE_URL=http://172\.[0-9.]*:8765|SPEECH_SERVICE_URL=http://127.0.0.1:8765|' \
      -e 's|^KNOWFLOW_BACKEND_URL=http://knowflow-backend:5000|KNOWFLOW_BACKEND_URL=http://127.0.0.1:5001|' \
      -e 's|^KNOWFLOW_BACKEND_URL=http://172\.[0-9.]*:5001|KNOWFLOW_BACKEND_URL=http://127.0.0.1:5001|' \
      -e 's|^RAGFLOW_API_URL=http://ragflow-server:9380|RAGFLOW_API_URL=http://127.0.0.1:9380|' \
      -e 's|^RAGFLOW_API_URL=http://172\.[0-9.]*:9380|RAGFLOW_API_URL=http://127.0.0.1:9380|' \
      -e 's|^KNOWFLOW_UI_URL=http://172\.[0-9.]*:9380|KNOWFLOW_UI_URL=http://127.0.0.1:9380|' "$tmp"
    sed_inplace -e '/^DEPLOY_HOST=/d' -e '/^FRONTEND_PORT=/d' "$tmp"
    mv "$tmp" "$ENV_FILE"
    info "已修复 platform/.env"
  fi
  if [[ ! -f "$KF_FILE" && -f "$LOCAL_KF_EXAMPLE" ]]; then
    cp "$LOCAL_KF_EXAMPLE" "$KF_FILE" && info "已创建 platform/knowflow.env"
  elif [[ -f "$KF_FILE" ]] && grep -q 'zxwei/knowflow:v2.1.8' "$KF_FILE" 2>/dev/null; then
    cp "$LOCAL_KF_EXAMPLE" "$KF_FILE" && info "已恢复 platform/knowflow.env（本地 arm64 配置）"
  fi
}

zhitan_knowflow_setup() {
  local TARGET="$PLATFORM/third_party/KnowFlow"
  local REPO="${KNOWFLOW_REPO:-https://github.com/knowflow-ai/KnowFlow.git}"
  local REF="${KNOWFLOW_REF:-main}"
  if [[ -d "$TARGET/.git" ]]; then
    info "KnowFlow 已存在，git pull …"
    git -C "$TARGET" pull --ff-only || true
  elif [[ ! -d "$TARGET" ]]; then
    info "克隆 KnowFlow …"
    mkdir -p "$(dirname "$TARGET")"
    git clone --depth 1 --branch "$REF" "$REPO" "$TARGET"
  fi
  local BASE_COMPOSE="$TARGET/docker/docker-compose-base.yml"
  if [[ -f "$BASE_COMPOSE" ]] && grep -q 'no-new-privileges:true' "$BASE_COMPOSE" 2>/dev/null; then
    sed -i.bak '/no-new-privileges:true/d' "$BASE_COMPOSE" 2>/dev/null || sed -i '' '/no-new-privileges:true/d' "$BASE_COMPOSE"
    rm -f "${BASE_COMPOSE}.bak"
  fi
  [[ -f "$PLATFORM/knowflow.env" ]] || cp "$PLATFORM/knowflow.env.example" "$PLATFORM/knowflow.env"
  local SETTINGS_YML="$TARGET/docker/knowflow-server/settings.yaml"
  [[ -f "$SETTINGS_YML" ]] || cp "$TARGET/docker/knowflow-server/settings.yaml.example" "$SETTINGS_YML"
  mkdir -p "$TARGET/docker/ragflow-logs"
  info "KnowFlow 源码就绪"
}

zhitan_knowflow_build() {
  local KF="$PLATFORM/third_party/KnowFlow"
  local ARCH="${KNOWFLOW_PLATFORM:-linux/arm64}"
  [[ -d "$KF" ]] || zhitan_knowflow_setup
  [[ -f "$PLATFORM/knowflow.env" ]] || cp "$PLATFORM/knowflow.env.example" "$PLATFORM/knowflow.env"
  # shellcheck source=/dev/null
  source "$PLATFORM/knowflow.env"
  ARCH="${KNOWFLOW_PLATFORM:-linux/arm64}"
  info "构建 KnowFlow 镜像 (${ARCH})，首次约 30–90 分钟"
  if [[ ! -d "$KF/huggingface.co/InfiniFlow/deepdoc" ]]; then
    export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
    python3 -m pip install -q huggingface_hub nltk 2>/dev/null || true
    bash "$SCRIPT_DIR/download_knowflow_deps_light.sh"
  fi
  if ! docker image inspect infiniflow/ragflow_deps:latest >/dev/null 2>&1; then
    docker build --platform "$ARCH" -f "$KF/Dockerfile.deps" -t infiniflow/ragflow_deps:latest "$KF"
  fi
  docker build --platform "$ARCH" --build-arg LIGHTEN="${KNOWFLOW_LIGHTEN:-1}" \
    --build-arg NEED_MIRROR="${KNOWFLOW_NEED_MIRROR:-1}" -f "$KF/Dockerfile" \
    -t knowflow-ragflow:source "$KF"
  docker build --platform "$ARCH" --build-arg NEED_MIRROR="${KNOWFLOW_NEED_MIRROR:-1}" \
    -f "$KF/knowflow/Dockerfile" --target backend -t knowflow-server:source "$KF/knowflow"
  info "完成: knowflow-ragflow:source, knowflow-server:source"
}

zhitan_stop() {
  cd "$PLATFORM"
  $COMPOSE --profile docker-app --profile docker-full down 2>/dev/null || $COMPOSE down
  [[ -f docker-compose.knowflow.yml ]] && docker compose -p knowflow -f docker-compose.knowflow.yml --env-file knowflow.env down 2>/dev/null || true
  [[ -f docker-compose.speech.yml ]] && docker compose -f docker-compose.speech.yml down 2>/dev/null || true
  for name_pid in "speech-api:$RUN_DIR/speech-api.pid" "pdf2zh API:$RUN_DIR/pdf2zh-api.pid" \
    "平台 API:$RUN_DIR/platform-api.pid" "Celery:$RUN_DIR/platform-worker.pid" "前端:$RUN_DIR/platform-frontend.pid"; do
    local name="${name_pid%%:*}" pid_file="${name_pid#*:}"
    [[ -f "$pid_file" ]] || continue
    local pid; pid="$(cat "$pid_file")"
    if kill -0 "$pid" 2>/dev/null; then info "停止 $name …"; kill "$pid" 2>/dev/null || true; pkill -P "$pid" 2>/dev/null || true; fi
    rm -f "$pid_file"
  done
  info "已停止"
}

usage() {
  cat <<EOF
用法: bash scripts/zhitan.sh <命令> [参数]

命令:
  start [local|speech|knowflow|docker|docker-full]   启动平台（默认 local）
  stop                                              停止
  env                                               修正本地 platform/.env
  knowflow setup | knowflow build                   KnowFlow 源码/镜像
  deploy [参数…]                                    远程部署（同 deploy.sh）

配置（仅两份模板）:
  platform/.env.example        → cp 为 .env（本地）
  platform/knowflow.env.example → cp 为 knowflow.env
  platform/deploy.target.example → cp 为 deploy.target（部署）

示例:
  bash scripts/zhitan.sh
  bash scripts/zhitan.sh knowflow
  bash scripts/zhitan.sh deploy
  bash scripts/zhitan.sh deploy full
EOF
}

main() {
  mkdir -p "$RUN_DIR" "$LOG_DIR"
  local cmd="${1:-start}"
  shift || true
  case "$cmd" in
    start|up)
      case "${1:-local}" in
        local|"") mode_local; print_urls ;;
        speech) mode_speech ;;
        knowflow) mode_knowflow ;;
        docker|hybrid) mode_docker; print_urls ;;
        docker-full) mode_docker_full; print_urls ;;
        *) usage; exit 1 ;;
      esac
      ;;
    stop) zhitan_stop ;;
    env|fix-env) zhitan_fix_local_env ;;
    knowflow)
      case "${1:-}" in
        setup) zhitan_knowflow_setup ;;
        build) zhitan_knowflow_build ;;
        *) error "用法: zhitan.sh knowflow setup|build"; exit 1 ;;
      esac
      ;;
    deploy) exec bash "$SCRIPT_DIR/deploy.sh" "$@" ;;
    -h|--help|help) usage ;;
    local|speech|knowflow|docker|docker-full|hybrid)
      main start "$cmd" "$@"
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
