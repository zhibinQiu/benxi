#!/usr/bin/env bash
# 生成仓库根 .env（合并 stack 模板 + platform/.env 密钥）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

STACK_EXAMPLE=".env.stack.example"
PLATFORM_ENV="platform/.env"
OUT=".env"

if [[ ! -f "$STACK_EXAMPLE" ]]; then
  echo "缺少 $STACK_EXAMPLE" >&2
  exit 1
fi

cp "$STACK_EXAMPLE" "$OUT"

append_if_set() {
  local key="$1" file="$2"
  local val
  val="$(grep -E "^${key}=" "$file" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\r' || true)"
  [[ -n "$val" ]] || return 0
  if grep -qE "^${key}=" "$OUT"; then
    if sed --version 2>/dev/null | grep -q GNU; then
      sed -i "s|^${key}=.*|${key}=${val}|" "$OUT"
    else
      sed -i '' "s|^${key}=.*|${key}=${val}|" "$OUT"
    fi
  else
    echo "${key}=${val}" >>"$OUT"
  fi
}

if [[ -f "$PLATFORM_ENV" ]]; then
  for key in JWT_SECRET DEEPSEEK_API_KEY DEEPSEEK_BASE_URL DEEPSEEK_MODEL \
    BOOTSTRAP_ADMIN_PHONE BOOTSTRAP_ADMIN_PASSWORD APP_NAME; do
    append_if_set "$key" "$PLATFORM_ENV"
  done
  echo "已合并 platform/.env 中的密钥到 $OUT"
else
  echo "提示: 复制 platform/.env.example → platform/.env 后再运行本脚本"
fi

# 生产栈：连接池档位 C（compose api/worker environment 会再覆盖 worker 池为 10/5）
for key in DB_POOL_SIZE DB_MAX_OVERFLOW DB_POOL_TIMEOUT DB_POOL_RECYCLE \
  STREAM_MAX_CONCURRENT_PER_WORKER STREAM_ACQUIRE_TIMEOUT BACKGROUND_JOBS_USE_CELERY; do
  if ! grep -qE "^${key}=" "$OUT" 2>/dev/null; then
    val="$(grep -E "^${key}=" "$STACK_EXAMPLE" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\r' || true)"
    [[ -n "$val" ]] && echo "${key}=${val}" >>"$OUT"
  fi
done

echo "已生成 $OUT（请检查 KNOWFLOW_ENABLED、ZHITAN_VERSION、FRONTEND_PORT）"
