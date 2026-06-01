#!/usr/bin/env bash
# 生成 amd64 服务器用 .env.docker / knowflow.env.docker（不修改本地 .env）
#
# 用法:
#   bash scripts/sync_deploy_env.sh
#   DEPLOY_HOST=192.168.1.10 bash scripts/sync_deploy_env.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="$ROOT/platform"
# 本地 Mac：.env + knowflow.env；服务器 amd64：.env.docker + knowflow.env.docker
SRC_ENV="$PLATFORM/.env"
OUT_ENV="$PLATFORM/.env.docker"
SRC_KF="$PLATFORM/knowflow.env"
OUT_KF="$PLATFORM/knowflow.env.docker"
LOCAL_KF_BACKUP="$PLATFORM/knowflow.env"
FALLBACK_ENV="$PLATFORM/.env.amd64.example"
FALLBACK_KF="$PLATFORM/knowflow.env.amd64.example"
DEPLOY_TARGET="${DEPLOY_TARGET:-$PLATFORM/deploy.target.amd64}"

load_deploy_target() {
  if [[ -f "$DEPLOY_TARGET" ]]; then
    # shellcheck disable=SC1090
    set -a && source "$DEPLOY_TARGET" && set +a
  fi
}

load_deploy_target

detect_host() {
  local ip="${DEPLOY_HOST:-}"
  [[ -n "$ip" ]] && { echo "$ip"; return; }
  ip="$(hostname -I 2>/dev/null | awk '{print $1}')" || true
  [[ -z "$ip" ]] && ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if ($i=="src") print $(i+1)}')" || true
  [[ -z "$ip" ]] && ip="127.0.0.1"
  echo "$ip"
}

sed_inplace() {
  if sed --version 2>/dev/null | grep -q GNU; then
    sed -i "$@"
  else
    sed -i '' "$@"
  fi
}

set_kv() {
  local file="$1" key="$2" val="$3"
  if grep -q "^${key}=" "$file" 2>/dev/null; then
    sed_inplace "s|^${key}=.*|${key}=${val}|" "$file"
  else
    echo "${key}=${val}" >>"$file"
  fi
}

sync_platform_env() {
  local host tmp
  host="$(detect_host)"
  tmp="$(mktemp)"

  if [[ -f "$SRC_ENV" ]]; then
    cp "$SRC_ENV" "$tmp"
    echo "[sync] 读取 platform/.env"
  elif [[ -f "$OUT_ENV" ]]; then
    cp "$OUT_ENV" "$tmp"
    echo "[sync] 更新 platform/.env.docker"
  elif [[ -f "$FALLBACK_ENV" ]]; then
    cp "$FALLBACK_ENV" "$tmp"
    echo "[sync] platform/.env.docker ← .env.amd64.example"
  else
    cp "$PLATFORM/.env.example" "$tmp"
    echo "[sync] platform/.env.docker ← .env.example"
  fi

  # 容器内服务地址（其余键值不动）
  sed_inplace \
    -e 's|@127\.0\.0\.1:5432|@postgres:5432|g' \
    -e 's|redis://127\.0\.0\.1:|redis://redis:|g' \
    -e 's|^MINIO_ENDPOINT=127\.0\.0\.1:9000|MINIO_ENDPOINT=minio:9000|' \
    -e 's|^MINIO_ENDPOINT=localhost:9000|MINIO_ENDPOINT=minio:9000|' \
    -e 's|^PDF2ZH_API_URL=http://127\.0\.0\.1:7861|PDF2ZH_API_URL=http://pdf2zh-api:7861|' \
    -e 's|^PDF2ZH_API_URL=http://localhost:7861|PDF2ZH_API_URL=http://pdf2zh-api:7861|' \
    -e 's|^SPEECH_SERVICE_URL=http://127\.0\.0\.1:8765|SPEECH_SERVICE_URL=http://speech-api:8765|' \
    -e 's|^SPEECH_SERVICE_URL=http://localhost:8765|SPEECH_SERVICE_URL=http://speech-api:8765|' \
    -e 's|^KNOWFLOW_BACKEND_URL=http://127\.0\.0\.1:5001|KNOWFLOW_BACKEND_URL=http://knowflow-backend:5000|' \
    -e 's|^KNOWFLOW_BACKEND_URL=http://localhost:5001|KNOWFLOW_BACKEND_URL=http://knowflow-backend:5000|' \
    -e 's|^RAGFLOW_API_URL=http://127\.0\.0\.1:9380|RAGFLOW_API_URL=http://ragflow-server:9380|' \
    -e 's|^RAGFLOW_API_URL=http://localhost:9380|RAGFLOW_API_URL=http://ragflow-server:9380|' \
    "$tmp"

  # 去掉 API Key 两侧引号
  sed_inplace 's|^DEEPSEEK_API_KEY="\([^"]*\)"|DEEPSEEK_API_KEY=\1|' "$tmp"

  # 宿主机模型目录 → 部署默认（挂载 .run/speech-models）
  if grep -q '^SPEECH_MODELS_DIR=' "$tmp"; then
    sed_inplace 's|^SPEECH_MODELS_DIR=.*|SPEECH_MODELS_DIR=|' "$tmp"
  fi

  set_kv "$tmp" KNOWFLOW_ENABLED true
  set_kv "$tmp" KNOWFLOW_UI_URL "http://${host}:9380"
  set_kv "$tmp" KNOWFLOW_UI_EMBED_MODE iframe
  set_kv "$tmp" DEPLOY_HOST "$host"
  set_kv "$tmp" FRONTEND_PORT "${FRONTEND_PORT:-40005}"

  grep -q '^KNOWFLOW_BACKEND_URL=' "$tmp" || set_kv "$tmp" KNOWFLOW_BACKEND_URL http://knowflow-backend:5000
  grep -q '^RAGFLOW_API_URL=' "$tmp" || set_kv "$tmp" RAGFLOW_API_URL http://ragflow-server:9380

  mv "$tmp" "$OUT_ENV"
  echo "[sync] DEPLOY_HOST=${host}，已写入 platform/.env.docker（不修改本地 .env）"
}

sync_knowflow_env() {
  local tmp
  tmp="$(mktemp)"

  if [[ -f "$LOCAL_KF_BACKUP" ]]; then
    cp "$LOCAL_KF_BACKUP" "$tmp"
    echo "[sync] 读取 platform/knowflow.env"
  elif [[ -f "$OUT_KF" ]]; then
    cp "$OUT_KF" "$tmp"
    echo "[sync] 更新 platform/knowflow.env.docker"
  elif [[ -f "$FALLBACK_KF" ]]; then
    cp "$FALLBACK_KF" "$tmp"
    echo "[sync] knowflow.env ← knowflow.env.amd64.example"
  else
    cp "$PLATFORM/knowflow.env.example" "$tmp"
    echo "[sync] knowflow.env ← knowflow.env.example"
  fi

  set_kv "$tmp" MACOS 0
  set_kv "$tmp" KNOWFLOW_DOCKER_NETWORK zhitanai_default
  set_kv "$tmp" RAGFLOW_IMAGE zxwei/knowflow:v2.1.8
  set_kv "$tmp" KNOWFLOW_SERVER_IMAGE zxwei/knowflow-server:v2.1.8
  sed_inplace '/^KNOWFLOW_PLATFORM=/d' "$tmp"

  mv "$tmp" "$OUT_KF"
  echo "[sync] 已写入 platform/knowflow.env.docker（amd64: zxwei/knowflow:v2.1.8）"
}

sync_platform_env
sync_knowflow_env
