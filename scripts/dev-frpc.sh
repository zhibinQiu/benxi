#!/usr/bin/env bash
# 本机 frpc：经 frp 暴露 Vite（API 由 Vite 反代）
# 由 ./dev.sh local 自动调用；也可 ./dev.sh frp start|stop|status|setup
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="$ROOT/platform"
RUN_DIR="$ROOT/.run"
LOG_DIR="$RUN_DIR/logs"
BIN_DIR="$RUN_DIR/frp"
PID_FILE="$RUN_DIR/dev-frpc.pid"
LOG_FILE="$LOG_DIR/dev-frpc.log"
TARGET_FILE="$PLATFORM/frp.target"
ENV_FILE="$PLATFORM/.env"
FRPC_BIN="$BIN_DIR/frpc"

FRP_ENABLED="${DEV_FRP:-}"
FRP_SERVER_ADDR="${FRP_SERVER_ADDR:-}"
FRP_SERVER_PORT="${FRP_SERVER_PORT:-40007}"
FRP_AUTH_TOKEN="${FRP_AUTH_TOKEN:-}"
FRP_LOCAL_PORT="${FRP_LOCAL_PORT:-40005}"
FRP_REMOTE_PORT="${FRP_REMOTE_PORT:-40010}"
FRP_VERSION="${FRP_VERSION:-0.69.1}"

read_env_key() {
  local key="$1"
  [[ -f "$ENV_FILE" ]] || return 0
  grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\r' || true
}

load_config() {
  if [[ -f "$TARGET_FILE" ]]; then
    # shellcheck disable=SC1090
    set -a && source "$TARGET_FILE" && set +a
  elif [[ -f "$PLATFORM/deploy.target" ]]; then
    # shellcheck disable=SC1090
    set -a && source "$PLATFORM/deploy.target" && set +a
  fi

  FRP_SERVER_ADDR="${FRP_SERVER_ADDR:-$(read_env_key REMOTE_HOST)}"
  FRP_SERVER_ADDR="${FRP_SERVER_ADDR:-172.19.134.45}"
  FRP_SERVER_PORT="${FRP_SERVER_PORT:-40007}"
  FRP_LOCAL_PORT="${FRP_LOCAL_PORT:-${LOCAL_DEV_WEB_PORT:-40005}}"
  FRP_REMOTE_PORT="${FRP_REMOTE_PORT:-40010}"
  FRP_VERSION="${FRP_VERSION:-0.69.1}"

  if [[ -z "$FRP_ENABLED" ]]; then
    if [[ -f "$TARGET_FILE" ]] && grep -qE '^FRP_ENABLED=(1|true|yes|on)$' "$TARGET_FILE" 2>/dev/null; then
      FRP_ENABLED=1
    else
      FRP_ENABLED=0
    fi
  fi
  case "$(printf '%s' "$FRP_ENABLED" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) FRP_ENABLED=1 ;;
    *) FRP_ENABLED=0 ;;
  esac
}

frpc_arch() {
  local os arch
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  arch="$(uname -m)"
  case "$arch" in
    x86_64|amd64) arch="amd64" ;;
    arm64|aarch64) arch="arm64" ;;
    *) echo "不支持的架构: $arch" >&2; return 1 ;;
  esac
  echo "${os}_${arch}"
}

ensure_frpc_binary() {
  mkdir -p "$BIN_DIR"
  if [[ -x "$FRPC_BIN" ]]; then
    return 0
  fi
  local plat tarball url tmp
  plat="$(frpc_arch)"
  tarball="frp_${FRP_VERSION}_${plat}.tar.gz"
  url="https://github.com/fatedier/frp/releases/download/v${FRP_VERSION}/${tarball}"
  tmp="$(mktemp -d)"
  echo "→ 下载 frpc ${FRP_VERSION} (${plat}) …"
  curl -fsSL -o "${tmp}/${tarball}" "$url"
  tar -xzf "${tmp}/${tarball}" -C "$tmp" "frp_${FRP_VERSION}_${plat}/frpc"
  install -m 755 "${tmp}/frp_${FRP_VERSION}_${plat}/frpc" "$FRPC_BIN"
  rm -rf "$tmp"
}

write_frpc_config() {
  local cfg="$BIN_DIR/frpc.toml"
  [[ -n "${FRP_AUTH_TOKEN:-}" ]] || {
    echo "缺少 FRP_AUTH_TOKEN，请 ./dev.sh frp setup" >&2
    return 1
  }
  cat >"$cfg" <<TOML
serverAddr = "${FRP_SERVER_ADDR}"
serverPort = ${FRP_SERVER_PORT}

auth.method = "token"
auth.token = "${FRP_AUTH_TOKEN}"

[[proxies]]
name = "local-dev-web"
type = "tcp"
localIP = "127.0.0.1"
localPort = ${FRP_LOCAL_PORT}
remotePort = ${FRP_REMOTE_PORT}
TOML
  echo "$cfg"
}

frpc_running() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
  fi
  pgrep -f "${FRPC_BIN} -c ${BIN_DIR}/frpc.toml" >/dev/null 2>&1
}

start_frpc() {
  load_config
  if [[ "$FRP_ENABLED" != "1" ]]; then
    return 0
  fi
  [[ -n "$FRP_SERVER_ADDR" ]] || {
    echo "未配置 FRP_SERVER_ADDR，请 cp platform/frp.target.example platform/frp.target" >&2
    return 1
  }

  if frpc_running; then
    echo "frpc 已在运行 → http://${FRP_SERVER_ADDR}:${FRP_REMOTE_PORT}/ai/"
    return 0
  fi

  ensure_frpc_binary
  local cfg
  cfg="$(write_frpc_config)"
  mkdir -p "$LOG_DIR"

  echo "→ 启动 frpc（本机 :${FRP_LOCAL_PORT} → ${FRP_SERVER_ADDR}:${FRP_REMOTE_PORT}）…"
  if [[ "$(uname -s)" != "Darwin" ]] && command -v setsid >/dev/null 2>&1; then
    setsid "$FRPC_BIN" -c "$cfg" >>"$LOG_FILE" 2>&1 </dev/null &
  else
    nohup "$FRPC_BIN" -c "$cfg" >>"$LOG_FILE" 2>&1 </dev/null &
    disown -h 2>/dev/null || true
  fi
  local pid=$!
  echo "$pid" >"$PID_FILE"

  local i
  for i in $(seq 1 10); do
    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
      if grep -q "login to server success" "$LOG_FILE" 2>/dev/null \
        || grep -q "start proxy success" "$LOG_FILE" 2>/dev/null; then
        echo "  frpc 已就绪（pid=${pid}）"
        echo "  他人访问: http://${FRP_SERVER_ADDR}:${FRP_REMOTE_PORT}/ai/"
        echo "  日志: ${LOG_FILE}"
        return 0
      fi
    else
      break
    fi
  done

  if kill -0 "$pid" 2>/dev/null; then
    echo "  frpc 已启动（pid=${pid}），等待日志确认…"
    echo "  他人访问: http://${FRP_SERVER_ADDR}:${FRP_REMOTE_PORT}/ai/"
    return 0
  fi

  echo "frpc 启动失败，见 ${LOG_FILE}：" >&2
  tail -8 "$LOG_FILE" 2>/dev/null || true
  rm -f "$PID_FILE"
  return 1
}

stop_frpc() {
  load_config
  local pid=""
  if [[ -f "$PID_FILE" ]]; then
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  fi
  if [[ -n "$pid" ]]; then
    kill "$pid" 2>/dev/null || true
    sleep 0.5
    kill -9 "$pid" 2>/dev/null || true
  fi
  pkill -f "${BIN_DIR}/frpc.toml" 2>/dev/null || true
  rm -f "$PID_FILE"
}

status_frpc() {
  load_config
  if [[ "$FRP_ENABLED" != "1" ]]; then
    echo "—   frpc（未启用，配置 platform/frp.target 或 DEV_FRP=1）"
    return 0
  fi
  if frpc_running; then
    echo "OK  frpc → http://${FRP_SERVER_ADDR}:${FRP_REMOTE_PORT}/ai/"
  else
    echo "DOWN frpc（未运行）"
  fi
}

setup_frpc() {
  local src="$PLATFORM/frp.target.example"
  local out="$TARGET_FILE"
  [[ -f "$src" ]] || { echo "缺少 ${src}" >&2; exit 1; }

  local host token
  host="$(read_env_key REMOTE_HOST)"
  if [[ -z "$host" && -f "$PLATFORM/deploy.target" ]]; then
    # shellcheck disable=SC1090
    set -a && source "$PLATFORM/deploy.target" && set +a
    host="${DEPLOY_HOST:-}"
  fi
  host="${host:-172.19.134.45}"

  if [[ ! -f "$out" ]]; then
    cp "$src" "$out"
    token="$(openssl rand -hex 16)"
    if sed --version 2>/dev/null | grep -q GNU; then
      sed -i "s|^FRP_SERVER_ADDR=.*|FRP_SERVER_ADDR=${host}|" "$out"
      sed -i "s|^FRP_AUTH_TOKEN=.*|FRP_AUTH_TOKEN=${token}|" "$out"
    else
      sed -i '' "s|^FRP_SERVER_ADDR=.*|FRP_SERVER_ADDR=${host}|" "$out"
      sed -i '' "s|^FRP_AUTH_TOKEN=.*|FRP_AUTH_TOKEN=${token}|" "$out"
    fi
    echo "已生成 ${out}（FRP_SERVER_ADDR=${host}）"
  else
    echo "已存在 ${out}，未覆盖"
  fi

  echo ""
  echo "下一步："
  echo "  1. 服务器安装 frps:  bash scripts/frp-server-install.sh"
  echo "  2. 本机启动 frpc:     ./dev.sh frp start"
  echo "  或一步:               ./dev.sh local（自动启动 frpc）"
}

cmd="${1:-status}"
case "$cmd" in
  start|up) start_frpc ;;
  stop|down) stop_frpc ;;
  status|st) status_frpc ;;
  setup) setup_frpc ;;
  restart)
    stop_frpc
    sleep 1
    start_frpc
    ;;
  -h|--help|help)
    sed -n '2,4p' "$0" | sed 's/^# \?//'
    echo "用法: ./dev.sh frp [setup|start|stop|status|restart|install-server]"
    ;;
  *)
    echo "未知命令: $cmd" >&2
    exit 1
    ;;
esac
