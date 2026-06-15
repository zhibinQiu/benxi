#!/usr/bin/env bash
# SSH 反向隧道：经服务器暴露本机 Vite（API 由 Vite 反代，仅需转发前端端口）
# 由 ./dev.sh local 自动调用；也可手动 ./dev.sh tunnel start|stop|status|setup
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="$ROOT/platform"
RUN_DIR="$ROOT/.run"
LOG_DIR="$RUN_DIR/logs"
PID_FILE="$RUN_DIR/dev-tunnel.pid"
LOG_FILE="$LOG_DIR/dev-tunnel.log"
TARGET_FILE="$PLATFORM/tunnel.target"
ENV_FILE="$PLATFORM/.env"

TUNNEL_ENABLED="${DEV_TUNNEL:-}"
TUNNEL_USER="${TUNNEL_USER:-root}"
TUNNEL_HOST="${TUNNEL_HOST:-}"
TUNNEL_REMOTE_PORT="${TUNNEL_REMOTE_PORT:-40010}"
TUNNEL_LOCAL_PORT="${TUNNEL_LOCAL_PORT:-40005}"
TUNNEL_BIND="${TUNNEL_BIND:-0.0.0.0}"

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
    TUNNEL_HOST="${TUNNEL_HOST:-${DEPLOY_HOST:-}}"
    TUNNEL_USER="${TUNNEL_USER:-${DEPLOY_USER:-root}}"
  fi

  TUNNEL_HOST="${TUNNEL_HOST:-$(read_env_key REMOTE_HOST)}"
  TUNNEL_USER="${TUNNEL_USER:-root}"
  TUNNEL_REMOTE_PORT="${TUNNEL_REMOTE_PORT:-40010}"
  TUNNEL_LOCAL_PORT="${TUNNEL_LOCAL_PORT:-${LOCAL_DEV_WEB_PORT:-40005}}"
  TUNNEL_BIND="${TUNNEL_BIND:-0.0.0.0}"

  if [[ -z "$TUNNEL_ENABLED" ]]; then
    if [[ -f "$TARGET_FILE" ]] && grep -qE '^TUNNEL_ENABLED=(1|true|yes|on)$' "$TARGET_FILE" 2>/dev/null; then
      TUNNEL_ENABLED=1
    else
      TUNNEL_ENABLED=0
    fi
  fi
  case "$(printf '%s' "$TUNNEL_ENABLED" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) TUNNEL_ENABLED=1 ;;
    *) TUNNEL_ENABLED=0 ;;
  esac
}

tunnel_forward_spec() {
  local bind="$1" remote="$2" local_port="$3"
  if [[ "$bind" == "127.0.0.1" || "$bind" == "localhost" ]]; then
    echo "${remote}:127.0.0.1:${local_port}"
  else
    echo "${bind}:${remote}:127.0.0.1:${local_port}"
  fi
}

tunnel_running() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
  fi
  local spec host
  spec="$(tunnel_forward_spec "$TUNNEL_BIND" "$TUNNEL_REMOTE_PORT" "$TUNNEL_LOCAL_PORT")"
  host="${TUNNEL_USER}@${TUNNEL_HOST}"
  pgrep -f "ssh.*-R ${spec//./\\.}.*${TUNNEL_HOST}" >/dev/null 2>&1 \
    || pgrep -f "ssh.*-R.*${TUNNEL_REMOTE_PORT}:127\\.0\\.0\\.1:${TUNNEL_LOCAL_PORT}.*@${TUNNEL_HOST}" >/dev/null 2>&1
}

start_tunnel() {
  load_config
  if [[ "$TUNNEL_ENABLED" != "1" ]]; then
    return 0
  fi
  [[ -n "$TUNNEL_HOST" ]] || {
    echo "未配置 TUNNEL_HOST，请 cp platform/tunnel.target.example platform/tunnel.target" >&2
    return 1
  }

  if tunnel_running; then
    echo "SSH 隧道已在运行 → http://${TUNNEL_HOST}:${TUNNEL_REMOTE_PORT}/ai/"
    return 0
  fi

  mkdir -p "$LOG_DIR"
  local spec ssh_target pid ssh_cmd
  spec="$(tunnel_forward_spec "$TUNNEL_BIND" "$TUNNEL_REMOTE_PORT" "$TUNNEL_LOCAL_PORT")"
  ssh_target="${TUNNEL_USER}@${TUNNEL_HOST}"

  local -a ssh_args=(
    -N
    -o BatchMode=yes
    -o ServerAliveInterval=30
    -o ServerAliveCountMax=3
    -o ExitOnForwardFailure=yes
    -o StrictHostKeyChecking=accept-new
    -R "$spec"
    "$ssh_target"
  )

  if command -v autossh >/dev/null 2>&1; then
    ssh_cmd=(autossh -M 0 "${ssh_args[@]}")
  else
    ssh_cmd=(ssh "${ssh_args[@]}")
  fi

  echo "→ 建立 SSH 反向隧道 ${spec} → ${ssh_target} …"
  if [[ "$(uname -s)" != "Darwin" ]] && command -v setsid >/dev/null 2>&1; then
    setsid "${ssh_cmd[@]}" >>"$LOG_FILE" 2>&1 </dev/null &
  else
    nohup "${ssh_cmd[@]}" >>"$LOG_FILE" 2>&1 </dev/null &
    disown -h 2>/dev/null || true
  fi
  pid=$!
  echo "$pid" >"$PID_FILE"

  local i
  for i in $(seq 1 8); do
    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
      echo "  隧道已就绪（pid=${pid}）"
      echo "  他人访问: http://${TUNNEL_HOST}:${TUNNEL_REMOTE_PORT}/ai/"
      echo "  日志: $LOG_FILE"
      return 0
    fi
  done

  echo "SSH 隧道启动失败，见 ${LOG_FILE}：" >&2
  tail -5 "$LOG_FILE" 2>/dev/null || true
  rm -f "$PID_FILE"
  return 1
}

stop_tunnel() {
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
  if [[ -n "${TUNNEL_HOST:-}" ]]; then
    pkill -f "ssh.*-R.*${TUNNEL_REMOTE_PORT}:127\\.0\\.0\\.1:${TUNNEL_LOCAL_PORT}.*@${TUNNEL_HOST}" 2>/dev/null || true
    pkill -f "autossh.*-R.*${TUNNEL_REMOTE_PORT}:127\\.0\\.0\\.1:${TUNNEL_LOCAL_PORT}.*@${TUNNEL_HOST}" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
}

status_tunnel() {
  load_config
  if [[ "$TUNNEL_ENABLED" != "1" ]]; then
    echo "—   SSH 隧道（未启用，配置 platform/tunnel.target 或 DEV_TUNNEL=1）"
    return 0
  fi
  if tunnel_running; then
    echo "OK  SSH 隧道 → http://${TUNNEL_HOST}:${TUNNEL_REMOTE_PORT}/ai/"
  else
    echo "DOWN SSH 隧道（未运行）"
  fi
}

setup_tunnel() {
  local src="$PLATFORM/tunnel.target.example"
  local out="$TARGET_FILE"
  [[ -f "$src" ]] || { echo "缺少 $src" >&2; exit 1; }
  if [[ -f "$out" ]]; then
    echo "已存在 ${out}，未覆盖"
    exit 0
  fi
  cp "$src" "$out"
  local host
  host="$(read_env_key REMOTE_HOST)"
  if [[ -z "$host" && -f "$PLATFORM/deploy.target" ]]; then
    # shellcheck disable=SC1090
    set -a && source "$PLATFORM/deploy.target" && set +a
    host="${DEPLOY_HOST:-}"
  fi
  host="${host:-172.19.134.45}"
  if sed --version 2>/dev/null | grep -q GNU; then
    sed -i "s|^TUNNEL_HOST=.*|TUNNEL_HOST=${host}|" "$out"
  else
    sed -i '' "s|^TUNNEL_HOST=.*|TUNNEL_HOST=${host}|" "$out"
  fi
  echo "已生成 ${out}（TUNNEL_HOST=${host}）"
  echo "请确认本机可 SSH 免密登录，服务器 sshd 已开 GatewayPorts。"
  echo "启动: ./dev.sh local"
}

cmd="${1:-status}"
case "$cmd" in
  start|up) start_tunnel ;;
  stop|down) stop_tunnel ;;
  status|st)
    status_tunnel
    ;;
  setup)
    setup_tunnel
    ;;
  restart)
    stop_tunnel
    sleep 1
    start_tunnel
    ;;
  -h|--help|help)
    sed -n '2,4p' "$0" | sed 's/^# \?//'
    echo "用法: ./dev.sh tunnel [setup|start|stop|status|restart]"
    ;;
  *)
    echo "未知命令: $cmd" >&2
    exit 1
    ;;
esac
