#!/bin/sh
# RAGFlow 容器健康检查：API 可达 + task_executor 进程存在 + Redis 队列无异常积压
set -eu

curl -fsS http://127.0.0.1/v1/system/config | grep -q '"code":0' || exit 1

if command -v pgrep >/dev/null 2>&1; then
  pgrep -f task_executor >/dev/null 2>&1 || exit 1
fi

REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"
LAG_THRESHOLD="${KNOWFLOW_HEALTHCHECK_MAX_LAG:-500}"
CONSUMER_GROUP="rag_flow_svr_task_broker"

check_queue_lag() {
  queue="$1"
  if ! command -v redis-cli >/dev/null 2>&1; then
    return 0
  fi
  auth=""
  if [ -n "$REDIS_PASSWORD" ]; then
    auth="-a $REDIS_PASSWORD"
  fi
  # shellcheck disable=SC2086
  lag="$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" $auth --raw XINFO GROUPS "$queue" 2>/dev/null \
    | awk -v grp="$CONSUMER_GROUP" '
      $1 == "name" && $2 == grp { show=1 }
      show && $1 == "lag" { print $2; exit }
    ')"
  if [ -z "$lag" ]; then
    return 0
  fi
  if [ "$lag" -gt "$LAG_THRESHOLD" ] 2>/dev/null; then
    echo "queue $queue lag=$lag > $LAG_THRESHOLD" >&2
    return 1
  fi
  return 0
}

check_queue_lag rag_flow_svr_queue
check_queue_lag rag_flow_svr_queue_1

exit 0
