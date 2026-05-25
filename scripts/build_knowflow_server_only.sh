#!/usr/bin/env bash
# 仅构建 knowflow-server:source（RAGFlow 镜像已存在时使用）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KF="$ROOT/platform/third_party/KnowFlow"
ARCH="${KNOWFLOW_PLATFORM:-linux/arm64}"
unset DOCKER_DEFAULT_PLATFORM DOCKER_PLATFORM
[[ -f "$ROOT/platform/knowflow.env" ]] && source "$ROOT/platform/knowflow.env"
docker build --platform "$ARCH" \
  --build-arg NEED_MIRROR="${KNOWFLOW_NEED_MIRROR:-1}" \
  -f "$KF/knowflow/Dockerfile" \
  --target backend \
  -t knowflow-server:source \
  "$KF/knowflow"
echo "完成: knowflow-server:source"
