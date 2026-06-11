#!/usr/bin/env bash
# 本机开发环境一键启动（API :8000 + 前端 Vite :40005 + 按需 Celery Worker）
#
# 用法:
#   bash start-local.sh          # 启动（会先停掉旧进程）
#   bash start-local.sh status   # 查看状态
#   bash start-local.sh stop     # 停止
#   bash start-local.sh restart  # 重启
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

cmd="${1:-start}"

case "$cmd" in
  start|up|"")
    exec bash "$ROOT/scripts/zhitan.sh" local-dev
    ;;
  status|st)
    exec bash "$ROOT/scripts/zhitan.sh" local-status
    ;;
  stop|down)
    # shellcheck source=scripts/lib/local-dev.sh
    source "$ROOT/scripts/lib/local-dev.sh"
    local_dev_stop
    echo "已停止本机 API / 前端 / Worker"
    ;;
  restart)
    bash "$0" stop
    sleep 1
    exec bash "$0" start
    ;;
  -h|--help|help)
    sed -n '2,9p' "$0" | sed 's/^# \?//'
    ;;
  *)
    echo "未知命令: $cmd" >&2
    echo "用法: bash start-local.sh [start|status|stop|restart]" >&2
    exit 1
    ;;
esac
