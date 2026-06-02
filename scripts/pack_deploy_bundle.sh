#!/usr/bin/env bash
# 打包可在 amd64 目标机解压部署的源码包（不含 .git / 虚拟环境 / 本地缓存）
#
# 用法:
#   bash scripts/pack_deploy_bundle.sh
#   scp dist/pdf_trans-deploy-*.tar.gz user@amd64-host:/opt/
#   ssh user@host 'cd /opt && tar xzf pdf_trans-deploy-*.tar.gz && cd pdf_trans && bash scripts/deploy.sh local full'
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$ROOT/dist"
STAMP="$(date +%Y%m%d-%H%M%S)"
NAME="pdf_trans-deploy-${STAMP}"
ARCHIVE="$OUT_DIR/${NAME}.tar.gz"

mkdir -p "$OUT_DIR"

STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

DEPLOY_ARCH="${DEPLOY_ARCH:-amd64}" bash "$ROOT/scripts/deploy.sh" _sync-env

echo "[pack] 准备打包目录（amd64 .env，不修改本机 platform/.env）..."
rsync -a \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='node_modules' \
  --exclude='.run' \
  --exclude='dist' \
  "$ROOT/" "$STAGING/pdf_trans/"
cp "$ROOT/platform/.env.docker" "$STAGING/pdf_trans/platform/.env"
[[ -f "$ROOT/platform/knowflow.env.docker" ]] && \
  cp "$ROOT/platform/knowflow.env.docker" "$STAGING/pdf_trans/platform/knowflow.env"

echo "[pack] 打包到 $ARCHIVE ..."
tar -czf "$ARCHIVE" -C "$STAGING" pdf_trans

ls -lh "$ARCHIVE"
echo "[pack] 完成。目标机（配置已与本地一致，无需再改密钥）:"
echo "  tar xzf $(basename "$ARCHIVE") && cd pdf_trans && bash scripts/deploy.sh local full"
