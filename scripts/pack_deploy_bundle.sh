#!/usr/bin/env bash
# 打包可在 amd64 目标机解压部署的源码包（不含 .git / 虚拟环境 / 本地缓存）
#
# 用法:
#   bash scripts/pack_deploy_bundle.sh
#   scp dist/pdf_trans-deploy-*.tar.gz user@amd64-host:/opt/
#   ssh user@amd64-host 'cd /opt && tar xzf pdf_trans-deploy-*.tar.gz && cd pdf_trans && bash scripts/deploy_amd64.sh'
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$ROOT/dist"
STAMP="$(date +%Y%m%d-%H%M%S)"
NAME="pdf_trans-deploy-${STAMP}"
ARCHIVE="$OUT_DIR/${NAME}.tar.gz"

mkdir -p "$OUT_DIR"

# 打包前同步：本地 .env → .env.docker，再复制为部署用 .env（打进压缩包，不提交 git）
bash "$ROOT/scripts/sync_deploy_env.sh"
cp "$ROOT/platform/.env.docker" "$ROOT/platform/.env"
cp "$ROOT/platform/knowflow.env.docker" "$ROOT/platform/knowflow.env"

echo "[pack] 打包到 $ARCHIVE（含与本地一致的 platform/.env、knowflow.env）..."
tar -czf "$ARCHIVE" \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='**/.venv' \
  --exclude='**/node_modules' \
  --exclude='.run' \
  --exclude='dist' \
  --exclude='**/__pycache__' \
  --exclude='*.pyc' \
  -C "$(dirname "$ROOT")" "$(basename "$ROOT")"

ls -lh "$ARCHIVE"
echo "[pack] 完成。目标机（配置已与本地一致，无需再改密钥）:"
echo "  tar xzf $(basename "$ARCHIVE") && cd pdf_trans && bash scripts/deploy_amd64.sh full"
