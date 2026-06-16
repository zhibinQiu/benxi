#!/usr/bin/env bash
# 宿主机启动 FunASR speech-api（模型缓存：项目 .run/speech-models）
# 入口: ./dev.sh speech local
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SVC="$ROOT/platform/speech-service"
RUN_DIR="$ROOT/.run"
LOG="$ROOT/.run/logs/speech-api.log"
PID_FILE="$RUN_DIR/speech-api.pid"
MODELS_DIR="${SPEECH_MODELS_DIR:-$ROOT/.run/speech-models}"

mkdir -p "$RUN_DIR/logs" "$MODELS_DIR"

if [[ -d "$ROOT/.run/modelscope" && ! -e "$MODELS_DIR/hub" ]]; then
  echo "[speech-local] 迁移旧缓存 .run/modelscope → .run/speech-models ..."
  shopt -s dotglob
  mv "$ROOT/.run/modelscope"/* "$MODELS_DIR/" 2>/dev/null || true
  rmdir "$ROOT/.run/modelscope" 2>/dev/null || true
fi

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "[speech-local] 已在运行 PID $(cat "$PID_FILE")"
  exit 0
fi

command -v ffmpeg >/dev/null || { echo "需要 ffmpeg: brew install ffmpeg"; exit 1; }

if [[ ! -x "$SVC/.venv/bin/uvicorn" ]]; then
  echo "[speech-local] 创建 venv 并安装依赖（首次较慢）..."
  python3 -m venv "$SVC/.venv"
  "$SVC/.venv/bin/pip" install -U pip
  "$SVC/.venv/bin/pip" install -r "$SVC/requirements.txt"
fi

echo "[speech-local] 模型目录: $MODELS_DIR"
echo "[speech-local] 启动 http://127.0.0.1:8765 ..."
nohup bash -c "cd '$SVC' && source .venv/bin/activate && export SPEECH_MODELS_DIR='$MODELS_DIR' MODELSCOPE_CACHE='$MODELS_DIR' && uvicorn app.main:app --host 127.0.0.1 --port 8765" >"$LOG" 2>&1 &
echo $! >"$PID_FILE"
echo "[speech-local] PID $(cat "$PID_FILE") 日志: $LOG"
