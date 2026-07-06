#!/bin/bash
# Chrome Debug Mode Launcher — for AI-Bridge
#
# 启动 Chrome 并开启 CDP 调试端口，让 AI-Bridge 可以通过 CDP 操控浏览器。
# 安全可重复执行（如已运行则跳过）。
#
# 用法:
#   bash packages/ai-bridge/scripts/start-chrome.sh
#
# 环境变量:
#   CDP_PORT=9222         # 调试端口 (默认 9222)
#   CHROMIUM_PATH=...     # Chrome 可执行文件路径
#   CHROME_PROFILE=...    # 用户数据目录（保存登录态）
#   PROXY_SERVER=...      # HTTP 代理（中国大陆用户需要）
#   HEADLESS=false        # 无头模式

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PACKAGE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── 颜色 ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
info()  { echo -e "${GREEN}[chrome]${NC} $*"; }
warn()  { echo -e "${YELLOW}[chrome]${NC} $*"; }
error() { echo -e "${RED}[chrome]${NC} $*" >&2; }

# ── 配置 ──
CDP_PORT="${CDP_PORT:-9222}"
CHROMIUM_PATH="${CHROMIUM_PATH:-}"
CHROME_PROFILE="${CHROME_PROFILE:-$HOME/.chrome-debug-profile}"
PROXY_SERVER="${PROXY_SERVER:-}"
HEADLESS="${HEADLESS:-false}"

LOG_FILE="${LOG_FILE:-/tmp/ai-bridge-chrome.log}"
PID_FILE="/tmp/ai-bridge-chrome.pid"

# ── 自动检测 Chrome 路径 ──
if [ -z "$CHROMIUM_PATH" ]; then
  if [[ "$(uname)" == "Darwin" ]]; then
    # macOS
    MAC_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if [ -f "$MAC_PATH" ]; then
      CHROMIUM_PATH="$MAC_PATH"
    elif [ -f "/Applications/Chromium.app/Contents/MacOS/Chromium" ]; then
      CHROMIUM_PATH="/Applications/Chromium.app/Contents/MacOS/Chromium"
    else
      # 尝试从 mdfind 查找
      CHROMIUM_PATH=$(mdfind "kMDItemKind == 'Application'" 2>/dev/null | grep -i chrome | head -1)
      if [ -n "$CHROMIUM_PATH" ] && [ -d "$CHROMIUM_PATH" ]; then
        CHROMIUM_PATH="$CHROMIUM_PATH/Contents/MacOS/$(basename "$CHROMIUM_PATH" .app)"
      fi
    fi
  elif command -v google-chrome-stable &>/dev/null; then
    CHROMIUM_PATH=$(command -v google-chrome-stable)
  elif command -v google-chrome &>/dev/null; then
    CHROMIUM_PATH=$(command -v google-chrome)
  elif command -v chromium-browser &>/dev/null; then
    CHROMIUM_PATH=$(command -v chromium-browser)
  elif command -v chromium &>/dev/null; then
    CHROMIUM_PATH=$(command -v chromium)
  fi
fi

if [ -z "$CHROMIUM_PATH" ] || [ ! -x "$CHROMIUM_PATH" ]; then
  error "未找到 Chrome/Chromium 可执行文件。"
  error "请设置 CHROMIUM_PATH 环境变量或安装 Google Chrome。"
  error ""
  error "  macOS: /Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
  error "  Linux: /usr/bin/google-chrome-stable"
  exit 1
fi

info "Chrome 路径: $CHROMIUM_PATH"

# ── 检查是否已在运行 ──
if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    # 检查 CDP 端口
    if curl -s "http://127.0.0.1:$CDP_PORT/json/version" >/dev/null 2>&1; then
      info "Chrome 调试模式已在运行 (PID: $OLD_PID, 端口: $CDP_PORT)"
      exit 0
    else
      warn "PID 文件存在但 CDP 端口 $CDP_PORT 无响应，清理旧进程..."
      kill "$OLD_PID" 2>/dev/null || true
      sleep 1
    fi
  else
    warn "PID 文件存在但进程已不存在，清理..."
  fi
  rm -f "$PID_FILE"
fi

# ── 准备用户数据目录 ──
mkdir -p "$CHROME_PROFILE"

# ── 构建启动参数 ──
ARGS=(
  "--remote-debugging-port=$CDP_PORT"
  "--user-data-dir=$CHROME_PROFILE"
  "--no-first-run"
  "--no-default-browser-check"
  "--disable-features=OptimizationHints"
  "--disable-features=MediaRouter"
  "--disable-background-networking"
  "--disable-sync"
  "--disable-translate"
)

if [ "$HEADLESS" = "true" ]; then
  ARGS+=("--headless=new")
fi

# 代理
if [ -n "$PROXY_SERVER" ]; then
  ARGS+=("--proxy-server=$PROXY_SERVER")
fi

# ── 启动 Chrome ──
info "启动 Chrome 调试模式 (端口 $CDP_PORT)..."
info "日志: $LOG_FILE"
info "配置: $CHROME_PROFILE"

nohup "$CHROMIUM_PATH" "${ARGS[@]}" > "$LOG_FILE" 2>&1 &
CHROME_PID=$!
echo "$CHROME_PID" > "$PID_FILE"

# ── 等待 CDP 就绪 ──
info "等待 CDP 就绪..."
for i in $(seq 1 30); do
  sleep 1
  if curl -s "http://127.0.0.1:$CDP_PORT/json/version" >/dev/null 2>&1; then
    info "✓ Chrome 调试模式已就绪 (PID: $CHROME_PID)"
    info "  CDP 地址: http://127.0.0.1:$CDP_PORT"
    info ""
    info "现在可以使用: node packages/ai-bridge/index.js chat \"你的问题\""
    exit 0
  fi
  if ! kill -0 "$CHROME_PID" 2>/dev/null; then
    error "Chrome 进程意外退出，检查日志:"
    tail -10 "$LOG_FILE" 2>/dev/null || true
    exit 1
  fi
  echo -n "."
done

error "Chrome 启动超时（30s），检查日志: $LOG_FILE"
exit 1
