#!/usr/bin/env bash
# 拉取 KnowFlow 官方 Docker 编排到 platform/third_party/KnowFlow
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$ROOT/platform/third_party/KnowFlow"
REPO="${KNOWFLOW_REPO:-https://github.com/knowflow-ai/KnowFlow.git}"
REF="${KNOWFLOW_REF:-main}"

if [[ -d "$TARGET/.git" ]]; then
  echo "[knowflow] 已存在 $TARGET，执行 git pull ..."
  git -C "$TARGET" pull --ff-only || true
elif [[ -d "$TARGET" ]]; then
  echo "[knowflow] 目录已存在（非 git 克隆），跳过拉取: $TARGET"
else
  echo "[knowflow] 克隆 $REPO -> $TARGET"
  mkdir -p "$(dirname "$TARGET")"
  git clone --depth 1 --branch "$REF" "$REPO" "$TARGET"
fi

# Docker Compose 2.x 校验：privileged 与重复 security_opt 会报错
BASE_COMPOSE="$TARGET/docker/docker-compose-base.yml"
if [[ -f "$BASE_COMPOSE" ]] && grep -q 'no-new-privileges:true' "$BASE_COMPOSE" 2>/dev/null; then
  sed -i.bak '/no-new-privileges:true/d' "$BASE_COMPOSE" && rm -f "${BASE_COMPOSE}.bak"
  echo "[knowflow] 已修补 docker-compose-base.yml（security_opt）"
fi
# 避免 include 后与 knowflow compose 中 external 网络定义冲突（仅删末尾 ragflow bridge 块）
if [[ -f "$BASE_COMPOSE" ]] && tail -1 "$BASE_COMPOSE" | grep -q 'bridge'; then
  head -n -4 "$BASE_COMPOSE" > "${BASE_COMPOSE}.nwtmp"
  mv "${BASE_COMPOSE}.nwtmp" "$BASE_COMPOSE"
  echo "[knowflow] 已修补 docker-compose-base.yml（networks.ragflow 改由 knowflow compose 定义）"
fi

ENV_SRC="$ROOT/platform/knowflow.env.example"
ENV_DST="$ROOT/platform/knowflow.env"
if [[ ! -f "$ENV_DST" ]]; then
  cp "$ENV_SRC" "$ENV_DST"
  echo "[knowflow] 已创建 platform/knowflow.env"
fi

SETTINGS_EX="$TARGET/docker/knowflow-server/settings.yaml.example"
SETTINGS_YML="$TARGET/docker/knowflow-server/settings.yaml"
[[ -f "$SETTINGS_YML" ]] || { cp "$SETTINGS_EX" "$SETTINGS_YML"; echo "[knowflow] 已创建 settings.yaml"; }
mkdir -p "$TARGET/docker/ragflow-logs"

echo "[knowflow] 完成。"
echo "  构建镜像: bash scripts/build_knowflow_source.sh"
echo "  启动平台: bash scripts/start_platform.sh knowflow"
