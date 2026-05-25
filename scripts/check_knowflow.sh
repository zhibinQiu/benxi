#!/usr/bin/env bash
# 轻量检查 KnowFlow（避免 docker ps/images 在 Desktop 繁忙时卡住）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="$ROOT/platform"
KF_PORT=5001
[[ -f "$PLATFORM/knowflow.env" ]] && grep -q '^KNOWFLOW_BACKEND_PORT=' "$PLATFORM/knowflow.env" \
  && KF_PORT=$(grep '^KNOWFLOW_BACKEND_PORT=' "$PLATFORM/knowflow.env" | cut -d= -f2)

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'
ok() { echo -e "${GREEN}[ok]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
fail() { echo -e "${RED}[fail]${NC} $*"; }

echo "=== KnowFlow 可达性（HTTP，不调用 docker CLI）==="
if curl -sf --max-time 3 "http://127.0.0.1:9380/" | head -c 20 | grep -q '<'; then
  ok "RAGFlow Web UI :9380 可访问（HTML）"
elif curl -sf --max-time 3 "http://127.0.0.1:9380" >/dev/null 2>&1; then
  warn "RAGFlow :9380 有响应但可能是 API JSON（应映射到 nginx:80，见 docker-compose.knowflow.yml）"
else
  fail "RAGFlow :9380 无响应 — 表 user/tenant/user_tenant 只能由 ragflow-server 首次启动时创建"
  echo "      请在 Docker Desktop 查看容器 ragflow-server 是否为 Running、架构是否为 arm64"
fi

if curl -sf --max-time 3 "http://127.0.0.1:${KF_PORT}/health" >/dev/null 2>&1; then
  ok "KnowFlow Backend :${KF_PORT}/health 正常"
else
  warn "KnowFlow Backend :${KF_PORT} 未就绪（若 RAGFlow 未起来，日志会一直「等待表创建」）"
fi

echo ""
echo "=== 说明 ==="
echo "1. Docker Desktop 显示 amd64：多为早期 1ms/预构建镜像 (zxwei/knowflow) 或 DOCKER_DEFAULT_PLATFORM=amd64 拉取的层，与 knowflow.env 里 KNOWFLOW_PLATFORM=arm64 可并存。"
echo "2. knowflow-backend 日志「等待 user, tenant, user_tenant」：正常等待 RAGFlow 建表；ragflow-server 崩溃或未启动时会一直循环。"
echo "3. 目标镜像标签：knowflow-ragflow:source、knowflow-server:source（需 bash scripts/build_knowflow_source.sh 完成后在 Desktop 里重建 ragflow-server）。"
