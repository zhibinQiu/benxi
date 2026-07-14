#!/usr/bin/env bash
# 将 BabelDOC 资源下载到项目目录 assets/babeldoc
# 用法: bash scripts/download_babeldoc_assets.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ASSETS_DIR="${ROOT}/assets/babeldoc"
CLI="${ROOT}/.venv/bin/pdf2zh_next"
CACHE_LINK="${HOME}/.cache/babeldoc"

mkdir -p "${ASSETS_DIR}"

if [[ -e "${CACHE_LINK}" && ! -L "${CACHE_LINK}" ]]; then
  echo "合并已有 ${CACHE_LINK} -> ${ASSETS_DIR}"
  rsync -a "${CACHE_LINK}/" "${ASSETS_DIR}/"
  rm -rf "${CACHE_LINK}"
fi

ln -sfn "${ASSETS_DIR}" "${CACHE_LINK}"
echo "已链接: ${CACHE_LINK} -> ${ASSETS_DIR}"

echo "下载资源（warmup）..."
cd "${ROOT}"
"${CLI}" --warmup

echo "打包到 assets/（生成 offline_assets_*.zip 备份）..."
"${CLI}" --generate-offline-assets "${ROOT}/assets"

echo ""
echo "完成。目录结构:"
du -sh "${ASSETS_DIR}"/* 2>/dev/null || true
echo "主路径: ${ASSETS_DIR}"
