#!/usr/bin/env bash
# 探测远程依赖（网关模式：HTTP 经 :40005/deps/…）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/platform/.env}"

GATEWAY_MODE=0
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source <(grep -E '^(REMOTE_HOST|REMOTE_GATEWAY_PORT|REMOTE_.*_PORT|GATEWAY_MODE)=' "$ENV_FILE" | tr -d '\r')
  if grep -qE '^REMOTE_GATEWAY_PORT=' "$ENV_FILE" 2>/dev/null \
    || grep -q '/deps/' "$ENV_FILE" 2>/dev/null; then
    GATEWAY_MODE=1
  fi
fi

HOST="${REMOTE_HOST:-172.19.134.45}"
GATEWAY_PORT="${REMOTE_GATEWAY_PORT:-40005}"
POSTGRES_PORT="${REMOTE_POSTGRES_PORT:-40002}"
REDIS_PORT="${REMOTE_REDIS_PORT:-40003}"
MINIO_PORT="${REMOTE_MINIO_PORT:-40004}"
MYSQL_PORT="${REMOTE_MYSQL_PORT:-40006}"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok=0
fail=0

check_tcp() {
  local name="$1" host="$2" port="$3"
  if nc -z -w 3 "$host" "$port" 2>/dev/null; then
    echo -e "${GREEN}OK${NC}  $name  tcp://${host}:${port}"
    ok=$((ok + 1))
  else
    echo -e "${RED}FAIL${NC}  $name  tcp://${host}:${port}"
    fail=$((fail + 1))
  fi
}

check_http() {
  local name="$1" url="$2"
  local code
  code="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 5 "$url" 2>/dev/null || echo "000")"
  if [[ "$code" =~ ^(200|204|301|302|307|401|403)$ ]]; then
    echo -e "${GREEN}OK${NC}  $name  $url  (HTTP $code)"
    ok=$((ok + 1))
  else
    echo -e "${RED}FAIL${NC}  $name  $url  (HTTP $code)"
    fail=$((fail + 1))
  fi
}

uses_local_pg=0
if [[ -f "$ENV_FILE" ]] && grep -qE '^DATABASE_URL=.*@127\.0\.0\.1:' "$ENV_FILE"; then
  uses_local_pg=1
  local_pg_port="${LOCAL_POSTGRES_PORT:-5432}"
  if grep -qE '^LOCAL_POSTGRES_PORT=' "$ENV_FILE"; then
    local_pg_port="$(grep -E '^LOCAL_POSTGRES_PORT=' "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '\r')"
  fi
fi

echo "远程依赖探测: ${HOST}（配置: ${ENV_FILE}）"
if [[ "$GATEWAY_MODE" == 1 ]]; then
  echo -e "${YELLOW}模式:${NC} gateway HTTP → :${GATEWAY_PORT}/deps/…"
fi
echo

if [[ "$uses_local_pg" -eq 1 ]]; then
  echo -e "${YELLOW}SKIP${NC}  PostgreSQL（本机 127.0.0.1:${local_pg_port}）"
  check_tcp "PostgreSQL (local)" "127.0.0.1" "$local_pg_port"
else
  check_tcp "PostgreSQL" "$HOST" "$POSTGRES_PORT"
fi
check_tcp "Redis" "$HOST" "$REDIS_PORT"
check_tcp "MinIO" "$HOST" "$MINIO_PORT"
check_tcp "RAGFlow MySQL" "$HOST" "$MYSQL_PORT"

if [[ "$GATEWAY_MODE" == 1 ]]; then
  check_http "Gateway pdf2zh" "http://${HOST}:${GATEWAY_PORT}/deps/pdf2zh/docs"
  check_http "KnowFlow Backend" "http://${HOST}:${GATEWAY_PORT}/deps/knowflow/health"
  check_http "RAGFlow API" "http://${HOST}:${GATEWAY_PORT}/deps/ragflow/v1/system/config"
  check_http "PDF 翻译 pdf2zh" "http://${HOST}:${GATEWAY_PORT}/deps/pdf2zh/docs"
  check_http "语音识别" "http://${HOST}:${GATEWAY_PORT}/deps/speech/health"
else
  PDF2ZH_PORT="${REMOTE_PDF2ZH_PORT:-40005}"
  SPEECH_PORT="${REMOTE_SPEECH_PORT:-40006}"
  KNOWFLOW_PORT="${REMOTE_KNOWFLOW_BACKEND_PORT:-40008}"
  check_http "KnowFlow Backend" "http://${HOST}:${KNOWFLOW_PORT}/health"
  check_http "PDF 翻译 pdf2zh" "http://${HOST}:${PDF2ZH_PORT}/docs"
  check_http "语音识别" "http://${HOST}:${SPEECH_PORT}/health"
fi
check_http "设计系统" "http://${HOST}:40001/"

echo
echo -e "结果: ${GREEN}${ok} 通过${NC}, ${fail} 失败"
if [[ "$fail" -gt 0 ]]; then
  echo -e "${YELLOW}提示:${NC} 服务器需 GATEWAY_MODE=1；见 deploy/gateway/README.md"
  exit 1
fi
