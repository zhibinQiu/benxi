#!/usr/bin/env bash
# 在远程服务器安装并启动 frps（仅需执行一次，或升级时重跑）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="$ROOT/backend"
ENV_FILE="$PLATFORM/.env"
FRP_TARGET="$PLATFORM/frp.target"
FRP_VERSION="${FRP_VERSION:-0.69.1}"
FRP_INSTALL_DIR="${FRP_INSTALL_DIR:-/opt/frp}"

read_env_key() {
  local key="$1"
  [[ -f "$ENV_FILE" ]] || return 0
  grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\r' || true
}

load_target() {
  FRP_SERVER_ADDR="${FRP_SERVER_ADDR:-$(read_env_key REMOTE_HOST)}"
  FRP_SERVER_PORT="${FRP_SERVER_PORT:-40007}"
  FRP_AUTH_TOKEN="${FRP_AUTH_TOKEN:-}"
  FRP_REMOTE_PORT="${FRP_REMOTE_PORT:-40010}"

  if [[ -f "$FRP_TARGET" ]]; then
    # shellcheck disable=SC1090
    set -a && source "$FRP_TARGET" && set +a
  fi
  if [[ -f "$PLATFORM/deploy.target" ]]; then
    # shellcheck disable=SC1090
    set -a && source "$PLATFORM/deploy.target" && set +a
    FRP_SERVER_ADDR="${FRP_SERVER_ADDR:-${DEPLOY_HOST:-}}"
  fi

  FRP_SERVER_ADDR="${FRP_SERVER_ADDR:-172.19.134.45}"
  FRP_SERVER_PORT="${FRP_SERVER_PORT:-40007}"
  FRP_REMOTE_PORT="${FRP_REMOTE_PORT:-40010}"
  SSH_USER="${SSH_USER:-${DEPLOY_USER:-root}}"
}

require_token() {
  if [[ -z "${FRP_AUTH_TOKEN:-}" ]]; then
    echo "缺少 FRP_AUTH_TOKEN，请先执行: ./dev.sh frp setup" >&2
    exit 1
  fi
}

install_remote() {
  load_target
  require_token

  local remote="$SSH_USER@${FRP_SERVER_ADDR}"
  local tarball="frp_${FRP_VERSION}_linux_amd64.tar.gz"
  local url="https://github.com/fatedier/frp/releases/download/v${FRP_VERSION}/${tarball}"

  echo "→ 安装 frps ${FRP_VERSION} 到 ${remote}:${FRP_INSTALL_DIR} …"

  ssh -o BatchMode=yes -o ConnectTimeout=15 "$remote" bash -s <<EOF
set -euo pipefail
INSTALL_DIR="${FRP_INSTALL_DIR}"
VERSION="${FRP_VERSION}"
TARBALL="${tarball}"
URL="${url}"
TOKEN="${FRP_AUTH_TOKEN}"
BIND_PORT="${FRP_SERVER_PORT}"

mkdir -p "\$INSTALL_DIR"
cd /tmp
if [[ ! -f "\$TARBALL" ]]; then
  curl -fsSL -o "\$TARBALL" "\$URL" || wget -q -O "\$TARBALL" "\$URL"
fi
tar -xzf "\$TARBALL" "frp_\${VERSION}_linux_amd64/frps"
install -m 755 "frp_\${VERSION}_linux_amd64/frps" "\$INSTALL_DIR/frps"
rm -rf "frp_\${VERSION}_linux_amd64"

cat >"\$INSTALL_DIR/frps.toml" <<TOML
bindAddr = "0.0.0.0"
bindPort = \${BIND_PORT}

auth.method = "token"
auth.token = "\${TOKEN}"

log.to = "/var/log/frps.log"
log.level = "info"
log.maxDays = 7
TOML

cat >/etc/systemd/system/frps.service <<UNIT
[Unit]
Description=frp server
After=network.target

[Service]
Type=simple
Restart=on-failure
RestartSec=5
ExecStart=\${INSTALL_DIR}/frps -c \${INSTALL_DIR}/frps.toml
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable frps
systemctl restart frps

if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active firewalld >/dev/null 2>&1; then
  firewall-cmd --permanent --add-port=\${BIND_PORT}/tcp 2>/dev/null || true
  firewall-cmd --permanent --add-port=${FRP_REMOTE_PORT}/tcp 2>/dev/null || true
  firewall-cmd --reload 2>/dev/null || true
fi

sleep 1
systemctl is-active frps
ss -tln | grep ":\${BIND_PORT} " || { echo "frps 未监听 \${BIND_PORT}" >&2; exit 1; }
echo "frps 已就绪 : \${BIND_PORT}"
EOF

  echo ""
  echo "frps 安装完成。"
  echo "  控制端口: ${FRP_SERVER_ADDR}:${FRP_SERVER_PORT}"
  echo "  本机启动 frpc: ./dev.sh frp start"
  echo "  他人访问: http://${FRP_SERVER_ADDR}:${FRP_REMOTE_PORT}/ai/"
}

install_remote "$@"
