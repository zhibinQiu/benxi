#!/usr/bin/env bash
# 在远程依赖服务器上创建并启用 Swap（缓解 15GB 内存 + 多容器 OOM）
#
# 用法:
#   SWAP_SIZE_GB=8 bash scripts/server-add-swap.sh
#   DEPLOY_HOST=172.19.134.45 DEPLOY_USER=root bash scripts/server-add-swap.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_USER="${DEPLOY_USER:-root}"
DEPLOY_HOST="${DEPLOY_HOST:-172.19.134.45}"
SWAP_SIZE_GB="${SWAP_SIZE_GB:-8}"
SWAP_FILE="${SWAP_FILE:-/swapfile}"

if [[ -f "$ROOT/backend/deploy.target" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/backend/deploy.target"
fi

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info() { echo -e "${GREEN}[add-swap]${NC} $*"; }
warn() { echo -e "${YELLOW}[add-swap]${NC} $*"; }
error() { echo -e "${RED}[add-swap]${NC} $*" >&2; }

info "远程配置 Swap: ${DEPLOY_USER}@${DEPLOY_HOST}  ${SWAP_SIZE_GB}GB → ${SWAP_FILE}"

ssh -o BatchMode=yes -o ConnectTimeout=60 -o ServerAliveInterval=15 \
  "${DEPLOY_USER}@${DEPLOY_HOST}" \
  "SWAP_SIZE_GB='${SWAP_SIZE_GB}' SWAP_FILE='${SWAP_FILE}'" bash -s <<'REMOTE'
set -euo pipefail

SWAP_SIZE_GB="${SWAP_SIZE_GB:-8}"
SWAP_FILE="${SWAP_FILE:-/swapfile}"
SWAP_BYTES=$((SWAP_SIZE_GB * 1024 * 1024 * 1024))

echo "=== 当前 Swap ==="
swapon --show || true
free -h | grep -i swap || true

current_gb="$(swapon --show=SIZE --noheadings --bytes 2>/dev/null | awk '{s+=$1} END {print int(s/1024/1024/1024+0.5)}')"
current_gb="${current_gb:-0}"
echo "已启用 Swap: ${current_gb}GB"

if [[ "$current_gb" -ge "$SWAP_SIZE_GB" ]]; then
  echo "Swap 已 >= ${SWAP_SIZE_GB}GB，跳过"
  exit 0
fi

if [[ -f "$SWAP_FILE" ]]; then
  if grep -q "$SWAP_FILE" /etc/fstab 2>/dev/null; then
    echo "Swap 文件已存在且已在 fstab，尝试 swapon …"
    chmod 600 "$SWAP_FILE"
    mkswap "$SWAP_FILE" >/dev/null 2>&1 || true
    swapon "$SWAP_FILE" 2>/dev/null || true
    swapon --show
    free -h | grep -i swap
    exit 0
  fi
  echo "移除旧 swap 文件以重建为 ${SWAP_SIZE_GB}GB …"
  swapoff "$SWAP_FILE" 2>/dev/null || true
  rm -f "$SWAP_FILE"
fi

avail_kb="$(df -k / | awk 'NR==2 {print $4}')"
need_kb=$((SWAP_SIZE_GB * 1024 * 1024))
if [[ "$avail_kb" -lt "$need_kb" ]]; then
  echo "根分区可用空间不足: 需要 ${SWAP_SIZE_GB}GB, 可用 $((avail_kb / 1024 / 1024))GB" >&2
  exit 1
fi

echo "创建 ${SWAP_SIZE_GB}GB swap 文件 ${SWAP_FILE} …"
if command -v fallocate >/dev/null 2>&1; then
  fallocate -l "${SWAP_BYTES}" "$SWAP_FILE"
else
  dd if=/dev/zero of="$SWAP_FILE" bs=1M count=$((SWAP_SIZE_GB * 1024)) status=progress
fi
chmod 600 "$SWAP_FILE"
mkswap "$SWAP_FILE"
swapon "$SWAP_FILE"

if ! grep -qF "$SWAP_FILE" /etc/fstab; then
  cp -a /etc/fstab "/etc/fstab.bak.$(date +%Y%m%d%H%M%S)"
  echo "$SWAP_FILE none swap sw 0 0" >> /etc/fstab
  echo "已写入 /etc/fstab"
fi

# 内存紧张时适度使用 swap，避免完全不用
if [[ -f /proc/sys/vm/swappiness ]]; then
  echo 10 > /proc/sys/vm/swappiness
  if ! grep -q '^vm.swappiness' /etc/sysctl.conf 2>/dev/null; then
    echo "vm.swappiness=10" >> /etc/sysctl.conf
  fi
fi

echo "=== 完成 ==="
swapon --show
free -h | grep -iE 'Mem|Swap'
REMOTE

info "Swap 配置完成"
