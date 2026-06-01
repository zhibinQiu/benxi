#!/usr/bin/env bash
# 确保 Mac 本地 platform/.env 使用本机地址，勿混入 amd64/远程部署配置
# 远程部署请用: bash scripts/sync_deploy_env.sh → platform/.env.docker（勿覆盖 .env）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="$ROOT/platform"
ENV_FILE="$PLATFORM/.env"
KF_FILE="$PLATFORM/knowflow.env"
LOCAL_ENV_EXAMPLE="$PLATFORM/.env.example"
LOCAL_KF_EXAMPLE="$PLATFORM/knowflow.env.example"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
info() { echo -e "${GREEN}[local-env]${NC} $*"; }
warn() { echo -e "${YELLOW}[local-env]${NC} $*"; }

sed_inplace() {
  if sed --version 2>/dev/null | grep -q GNU; then
    sed -i "$@"
  else
    sed -i '' "$@"
  fi
}

# 本地 .env 中不应出现的部署/远程特征
needs_local_fix() {
  [[ -f "$ENV_FILE" ]] || return 1
  grep -qE \
    '@postgres:|@postgres/|redis://redis:|^MINIO_ENDPOINT=minio:|^SPEECH_SERVICE_URL=http://speech-api:|^KNOWFLOW_BACKEND_URL=http://knowflow-backend:|^RAGFLOW_API_URL=http://ragflow-server:|^KNOWFLOW_UI_URL=http://172\.|^RAGFLOW_API_URL=http://172\.|^KNOWFLOW_BACKEND_URL=http://172\.|^SPEECH_SERVICE_URL=http://172\.|^DEPLOY_HOST=|^FRONTEND_PORT=' \
    "$ENV_FILE"
}

fix_platform_env() {
  if [[ ! -f "$ENV_FILE" ]]; then
    if [[ -f "$LOCAL_ENV_EXAMPLE" ]]; then
      cp "$LOCAL_ENV_EXAMPLE" "$ENV_FILE"
      info "已创建 platform/.env ← .env.example"
    else
      warn "缺少 platform/.env.example，无法自动创建 .env"
    fi
    return
  fi

  if ! needs_local_fix; then
    return
  fi

  warn "检测到 platform/.env 混入远程/Docker 部署配置，正在改回本地开发地址…"
  local tmp
  tmp="$(mktemp)"
  cp "$ENV_FILE" "$tmp"
  sed_inplace \
    -e 's|@postgres:5432|@127.0.0.1:5433|g' \
    -e 's|@postgres/|@127.0.0.1:5433/|g' \
    -e 's|^REDIS_URL=redis://redis:|REDIS_URL=redis://127.0.0.1:|g' \
    -e 's|^MINIO_ENDPOINT=minio:9000|MINIO_ENDPOINT=127.0.0.1:9000|' \
    -e 's|^PDF2ZH_API_URL=http://pdf2zh-api:7861|PDF2ZH_API_URL=http://127.0.0.1:7861|' \
    -e 's|^SPEECH_SERVICE_URL=http://speech-api:8765|SPEECH_SERVICE_URL=http://127.0.0.1:8765|' \
    -e 's|^SPEECH_SERVICE_URL=http://172\.[0-9.]*:8765|SPEECH_SERVICE_URL=http://127.0.0.1:8765|' \
    -e 's|^KNOWFLOW_BACKEND_URL=http://knowflow-backend:5000|KNOWFLOW_BACKEND_URL=http://127.0.0.1:5001|' \
    -e 's|^KNOWFLOW_BACKEND_URL=http://172\.[0-9.]*:5001|KNOWFLOW_BACKEND_URL=http://127.0.0.1:5001|' \
    -e 's|^RAGFLOW_API_URL=http://ragflow-server:9380|RAGFLOW_API_URL=http://127.0.0.1:9380|' \
    -e 's|^RAGFLOW_API_URL=http://172\.[0-9.]*:9380|RAGFLOW_API_URL=http://127.0.0.1:9380|' \
    -e 's|^KNOWFLOW_UI_URL=http://172\.[0-9.]*:9380|KNOWFLOW_UI_URL=http://127.0.0.1:9380|' \
    "$tmp"
  # 部署专用键不应留在本地 .env
  sed_inplace \
    -e '/^DEPLOY_HOST=/d' \
    -e '/^FRONTEND_PORT=/d' \
    "$tmp"
  mv "$tmp" "$ENV_FILE"
  info "已修复 platform/.env（本机 KnowFlow / 会议助手 / 基础设施地址）"
  info "远程部署请使用 platform/.env.docker，勿 sync 覆盖本地 .env"
}

fix_knowflow_env() {
  if [[ ! -f "$KF_FILE" ]]; then
    if [[ -f "$LOCAL_KF_EXAMPLE" ]]; then
      cp "$LOCAL_KF_EXAMPLE" "$KF_FILE"
      info "已创建 platform/knowflow.env ← knowflow.env.example"
    fi
    return
  fi

  if grep -q 'zxwei/knowflow:v2.1.8' "$KF_FILE" 2>/dev/null; then
    warn "knowflow.env 含 amd64 预构建镜像，改回 Mac arm64 配置…"
    if [[ -f "$LOCAL_KF_EXAMPLE" ]]; then
      cp "$LOCAL_KF_EXAMPLE" "$KF_FILE"
      info "已恢复 platform/knowflow.env ← knowflow.env.example"
    fi
  fi
}

fix_platform_env
fix_knowflow_env
