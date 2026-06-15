#!/usr/bin/env bash
# 生成本地 remote-dev 用的 platform/.env（依赖指向远程服务器）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="$ROOT/platform"
REMOTE_HOST="${REMOTE_HOST:-172.19.134.45}"
SRC="$PLATFORM/.env.remote.example"
OUT="$PLATFORM/.env"

if [[ ! -f "$SRC" ]]; then
  echo "缺少 $SRC" >&2
  exit 1
fi

sed_inplace() {
  if sed --version 2>/dev/null | grep -q GNU; then
    sed -i "$@"
  else
    sed -i '' "$@"
  fi
}

OLD_BACKUP=""
if [[ -f "$OUT" ]]; then
  OLD_BACKUP="$(mktemp)"
  cp "$OUT" "$OLD_BACKUP"
fi

cp "$SRC" "$OUT"
sed_inplace "s|172\\.19\\.134\\.45|${REMOTE_HOST}|g" "$OUT"
sed_inplace "s|^REMOTE_HOST=.*|REMOTE_HOST=${REMOTE_HOST}|" "$OUT"

merge_key() {
  local key="$1" old_file="$2"
  [[ -f "$old_file" ]] || return 0
  local val
  val="$(grep -E "^${key}=" "$old_file" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\r' || true)"
  [[ -n "$val" ]] || return 0
  if grep -qE "^${key}=" "$OUT"; then
    sed_inplace "s|^${key}=.*|${key}=${val}|" "$OUT"
  else
    echo "${key}=${val}" >>"$OUT"
  fi
}

if [[ -n "$OLD_BACKUP" ]]; then
  for key in JWT_SECRET DEEPSEEK_API_KEY DEEPSEEK_BASE_URL DEEPSEEK_MODEL \
    BOOTSTRAP_ADMIN_PHONE BOOTSTRAP_ADMIN_PASSWORD BOOTSTRAP_ADMIN_USERNAME BOOTSTRAP_ADMIN_EMAIL \
    ACCESS_TOKEN_EXPIRE_MINUTES SMART_DATA_QUERY_V2_DIFY_API_KEY CARBON_QA_V2_CHAT_API_KEY \
    PLATFORM_LLM_API_KEY PLATFORM_LLM_BASE_URL PLATFORM_LLM_MODEL \
    PLATFORM_EMBEDDING_API_KEY PLATFORM_EMBEDDING_BASE_URL PLATFORM_EMBEDDING_MODEL PLATFORM_EMBEDDING_FACTORY \
    PLATFORM_VL_API_KEY PLATFORM_VL_BASE_URL PLATFORM_VL_MODEL \
    PLATFORM_RERANK_API_KEY PLATFORM_RERANK_BASE_URL PLATFORM_RERANK_MODEL \
    PLATFORM_PADDLEOCR_BASE_URL PLATFORM_PADDLEOCR_API_KEY PLATFORM_PADDLEOCR_MODEL \
    PLATFORM_PADDLEOCR_URL RAGFLOW_API_KEY \
    RAGFLOW_SHARED_EMAIL RAGFLOW_SHARED_PASSWORD \
    RAGFLOW_LLM_TEMPLATE_EMAIL SMART_DATA_QUERY_PATH CARBON_QA_PATH \
    SMART_FORECAST_PROXY_PREFIX; do
    merge_key "$key" "$OLD_BACKUP"
  done
  rm -f "$OLD_BACKUP"
fi

echo "已生成 ${OUT}（REMOTE_HOST=${REMOTE_HOST}）"
echo "验证远程依赖: bash scripts/verify-remote-deps.sh"
echo "同步资源配置菜单: cd platform && python scripts/sync_resource_settings_from_env.py --force"
echo "启动本机 dev: ./dev.sh local"
