#!/usr/bin/env bash
# 从源码构建 KnowFlow / RAGFlow Docker 镜像（arm64 / Apple Silicon）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="$ROOT/platform"
KF="$PLATFORM/third_party/KnowFlow"
ARCH="${KNOWFLOW_PLATFORM:-linux/arm64}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
info() { echo -e "${GREEN}[build]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }

[[ -d "$KF" ]] || { bash "$ROOT/scripts/setup_knowflow.sh"; }

SETTINGS="$PLATFORM/third_party/KnowFlow/docker/knowflow-server/settings.yaml"
if [[ ! -f "$SETTINGS" ]]; then
  cp "$PLATFORM/third_party/KnowFlow/docker/knowflow-server/settings.yaml.example" "$SETTINGS"
  info "已创建 knowflow-server/settings.yaml"
fi

mkdir -p "$PLATFORM/third_party/KnowFlow/docker/ragflow-logs"

[[ -f "$PLATFORM/knowflow.env" ]] || cp "$PLATFORM/knowflow.env.example" "$PLATFORM/knowflow.env"
# shellcheck source=/dev/null
[[ -f "$PLATFORM/knowflow.env" ]] && source "$PLATFORM/knowflow.env"
ARCH="${KNOWFLOW_PLATFORM:-linux/arm64}"

info "目标架构: ${ARCH} (首次构建 deps + RAGFlow 约 30-90 分钟)"

if [[ ! -d "$KF/huggingface.co/InfiniFlow/deepdoc" ]]; then
  info "[0/4] 下载 LIGHTEN 构建依赖 ..."
  export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
  python3 -m pip install -q huggingface_hub nltk 2>/dev/null || true
  bash "$ROOT/scripts/download_knowflow_deps_light.sh"
fi

if ! docker image inspect infiniflow/ragflow_deps:latest >/dev/null 2>&1; then
  info "[1/4] 构建 ragflow_deps ..."
  docker build --platform "$ARCH" \
    -f "$KF/Dockerfile.deps" \
    -t infiniflow/ragflow_deps:latest \
    "$KF"
else
  info "[1/4] 已存在 infiniflow/ragflow_deps:latest，跳过"
fi

info "[2/4] 构建 RAGFlow (LIGHTEN=1) ..."
docker build --platform "$ARCH" \
  --build-arg LIGHTEN="${KNOWFLOW_LIGHTEN:-1}" \
  --build-arg NEED_MIRROR="${KNOWFLOW_NEED_MIRROR:-1}" \
  -f "$KF/Dockerfile" \
  -t knowflow-ragflow:source \
  "$KF"

info "[3/4] 构建 KnowFlow Server ..."
docker build --platform "$ARCH" \
  --build-arg NEED_MIRROR="${KNOWFLOW_NEED_MIRROR:-1}" \
  -f "$KF/knowflow/Dockerfile" \
  --target backend \
  -t knowflow-server:source \
  "$KF/knowflow"

info "[4/4] 完成"
info "源码镜像: knowflow-ragflow:source, knowflow-server:source"
info "启动栈: bash scripts/start_platform.sh knowflow  # 使用 platform/docker-compose.knowflow.yml"
