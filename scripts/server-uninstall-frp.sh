#!/usr/bin/env bash
# 卸载远程服务器 frps（本机 remote-dev 改走 /deps/ 网关，不再需要 frp）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="$ROOT/platform"

DEPLOY_USER="${DEPLOY_USER:-root}"
DEPLOY_HOST="${DEPLOY_HOST:-172.19.134.45}"
FRP_INSTALL_DIR="${FRP_INSTALL_DIR:-/opt/frp}"

if [[ -f "$PLATFORM/deploy.target" ]]; then
  # shellcheck disable=SC1090
  set -a && source "$PLATFORM/deploy.target" && set +a
fi

echo "→ 卸载 ${DEPLOY_USER}@${DEPLOY_HOST} 上的 frps …"
ssh -o BatchMode=yes -o ConnectTimeout=15 "${DEPLOY_USER}@${DEPLOY_HOST}" bash -s <<EOF
set -euo pipefail
systemctl stop frps 2>/dev/null || true
systemctl disable frps 2>/dev/null || true
pkill -x frps 2>/dev/null || true
rm -f /etc/systemd/system/frps.service
systemctl daemon-reload 2>/dev/null || true
rm -rf '${FRP_INSTALL_DIR}'
echo "frps 已卸载"
ss -tlnp 2>/dev/null | grep -E ':40007|:40008' || echo "40007/40008 已无 frp 监听"
EOF

echo "完成。本机请勿再使用 ./dev.sh frp；远程依赖经 http://${DEPLOY_HOST}:40005/deps/…"
