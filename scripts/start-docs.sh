#!/usr/bin/env bash
# 宿主机启动 MkDocs 文档站（热重载 docs/zh）
# 入口: ./dev.sh docs local
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT/.run"
VENV="$RUN_DIR/docs-venv"
LOG="$RUN_DIR/logs/docs.log"
PID_FILE="$RUN_DIR/docs.pid"
PORT="${DOCS_PORT:-40100}"

mkdir -p "$RUN_DIR/logs"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "[docs-local] 已在运行 PID $(cat "$PID_FILE") → http://127.0.0.1:${PORT}/"
  exit 0
fi

if [[ ! -x "$VENV/bin/mkdocs" ]]; then
  echo "[docs-local] 创建 venv 并安装 MkDocs（首次较慢）..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -U pip
  "$VENV/bin/pip" install -r "$ROOT/docs/requirements-docs.txt"
fi

echo "[docs-local] 启动 http://127.0.0.1:${PORT}/ ..."
cd "$ROOT"
nohup "$VENV/bin/mkdocs" serve -a "127.0.0.1:${PORT}" >"$LOG" 2>&1 &
echo $! >"$PID_FILE"
echo "[docs-local] PID $(cat "$PID_FILE") 日志: $LOG"
