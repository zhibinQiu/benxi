#!/usr/bin/env bash
# 本地 / 容器：editable 安装全部 AgentKit 子包 + platform（避免 pip 覆盖为 wheel）
#
# 环境变量:
#   PACKAGES_DIR      默认 <repo>/packages；容器内常为 /packages
#   PLATFORM_DIR      默认 <repo>/platform；容器内常为 /app
#   INSTALL_PLATFORM_DEPS=1  同时安装 platform 的 pip 依赖（Docker 构建时用）
#   PYTHON            默认 python3.11
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PACKAGES_DIR="${PACKAGES_DIR:-${ROOT}/packages}"
PLATFORM_DIR="${PLATFORM_DIR:-${ROOT}/platform}"
PY="${PYTHON:-python3.11}"

AGENTKIT_PKGS=(
  agentkit-skills
  agentkit-mcp
  agentkit-aip
  agentkit-route
  agentkit-loop
  agentkit-subagent
  agentkit-orchestrate
)

for pkg in "${AGENTKIT_PKGS[@]}"; do
  "$PY" -m pip install -e "${PACKAGES_DIR}/${pkg}" --no-deps -q
done

if [[ "${INSTALL_PLATFORM_DEPS:-0}" == "1" ]]; then
  "$PY" -m pip install -e "${PLATFORM_DIR}" -q
else
  "$PY" -m pip install -e "${PLATFORM_DIR}" --no-deps -q
fi
echo "AgentKit + platform editable install done."
