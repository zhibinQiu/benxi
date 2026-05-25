#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="$ROOT/platform"
RUN_DIR="$ROOT/.run"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.local.yml"

stop_pid_file() {
  local name="$1" pid_file="$2"
  [[ -f "$pid_file" ]] || return 0
  local pid
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" 2>/dev/null; then
    echo "[stop] 停止 $name (PID $pid) ..."
    kill "$pid" 2>/dev/null || true
    # 子进程（bash -c / npm / uvicorn reload）
    pkill -P "$pid" 2>/dev/null || true
  fi
  rm -f "$pid_file"
}

echo "[stop] 停止 Docker 服务 ..."
cd "$PLATFORM"
$COMPOSE --profile docker-app --profile docker-full down 2>/dev/null || $COMPOSE down
if [[ -f docker-compose.knowflow.yml ]]; then
  docker compose -p knowflow -f docker-compose.knowflow.yml --env-file knowflow.env down 2>/dev/null || true
fi
if [[ -f docker-compose.speech.yml ]]; then
  docker compose -f docker-compose.speech.yml down 2>/dev/null || true
fi

stop_pid_file "speech-api"       "$RUN_DIR/speech-api.pid"
stop_pid_file "pdf2zh API"       "$RUN_DIR/pdf2zh-api.pid"
stop_pid_file "平台 API"         "$RUN_DIR/platform-api.pid"
stop_pid_file "Celery Worker"    "$RUN_DIR/platform-worker.pid"
stop_pid_file "平台前端"         "$RUN_DIR/platform-frontend.pid"

echo "[stop] 完成"
