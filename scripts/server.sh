#!/usr/bin/env bash
# 服务器运维管理：重启/状态/构建/日志
#
# 由 ./dev.sh server 调用，勿直接执行。
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
BOLD='\033[1m'

info()  { echo -e "${GREEN}[server]${NC} $*"; }
warn()  { echo -e "${YELLOW}[server]${NC} $*"; }
error() { echo -e "${RED}[server]${NC} $*" >&2; }

DEPLOY_USER="${DEPLOY_USER:-root}"
DEPLOY_HOST="${DEPLOY_HOST:-172.19.134.45}"
DEPLOY_PATH="${DEPLOY_PATH:-/root/qzb/benxi}"

# --- SSH 包装 ---
remote() {
  ssh -o BatchMode=yes -o ConnectTimeout=15 "${DEPLOY_USER}@${DEPLOY_HOST}" "$@"
}

# --- 辅助函数 ---
usage() {
  cat <<EOF
用法: ./dev.sh server <命令> [选项]

命令:
  restart             构建并重启服务器所有服务（含编译）
  restart --base      只重启基础服务（postgres/redis/minio/pdf2zh-api/speech-api 等）
  restart --service <名称>  只重启指定服务（如 api worker frontend）
  status              查看服务器所有服务状态（彩色指示灯）
  build               在服务器构建镜像
  logs [服务名]       查看服务器日志
  pull                拉取最新代码并重启（不含编译，快速生效）

环境变量:
  DEPLOY_HOST         服务器地址（默认 172.19.134.45）
  DEPLOY_PATH         项目路径（默认 /root/qzb/benxi）
  DEPLOY_USER         SSH 用户（默认 root）
EOF
}

# --- 健康检查辅助函数 ---
wait_service_healthy() {
  local name="$1"
  local check_cmd="$2"
  local timeout="${3:-60}"
  local label="${4:-$name}"

  info "等待 $label 就绪（最长 ${timeout}s）..."
  local i
  for i in $(seq 1 "$timeout"); do
    if remote docker exec "$(remote docker ps -q -f name="$name" 2>/dev/null | head -1)" sh -c "$check_cmd" 2>/dev/null; then
      echo "  [${i}s] $label 已就绪"
      return 0
    fi
    sleep 2
  done
  warn "$label 未在 ${timeout}s 内就绪，请检查日志"
  return 1
}

# --- 状态检查函数（返回 OC 退出码）---
check_container() {
  local svc="$1"
  local label="$2"
  local check="$3"

  local cid status
  # 优先匹配 benxi 项目容器（避免被其他同名容器干扰）
  cid=$(remote docker ps -q -f "name=benxi-${svc}" 2>/dev/null || true)
  # 回退到宽匹配（用于 knowflow/ragflow 等非 benxi 容器）
  if [[ -z "$cid" ]]; then
    cid=$(remote docker ps -q -f "name=${svc}" 2>/dev/null || true)
  fi
  if [[ -z "$cid" ]]; then
    echo -e "  ${RED}[DOWN]${NC} $label"
    return 1
  fi
  if [[ -n "$check" ]]; then
    # 用单引号包裹 check 命令，防止远端 shell 展开其中的变量/管道符
    if remote docker exec "$cid" sh -c "'$check'" 2>/dev/null; then
      echo -e "  ${GREEN}[OK]${NC} $label"
      return 0
    else
      status=$(remote docker inspect "$cid" --format '{{.State.Health.Status}}' 2>/dev/null || echo "unknown")
      echo -e "  ${YELLOW}[WARN]${NC} $label (health=$status)"
      return 2
    fi
  fi
  echo -e "  ${GREEN}[OK]${NC} $label (running)"
  return 0
}

# --- 全部重启（含编译）---
server_restart_all() {
  info "=== 服务器全量重启（含编译）==="
  info "目标: ${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}"

  remote "echo ok" >/dev/null || { error "SSH 连接失败"; exit 1; }

  # 检测架构
  local arch
  arch=$(remote "uname -m" 2>/dev/null || echo "x86_64")

  info "服务器架构: $arch"
  info "第1步: 构建镜像..."

  # 构建 —— 根据是否有 knowflow profile 决定
  local profiles
  profiles=$(remote "cd '${DEPLOY_PATH}' && grep -l knowflow .env 2>/dev/null || true")
  if [[ -n "$profiles" ]]; then
    remote "cd '${DEPLOY_PATH}' && bash scripts/stack.sh build --profile knowflow --profile speech 2>&1"
  else
    remote "cd '${DEPLOY_PATH}' && bash scripts/stack.sh build 2>&1"
  fi

  info "第2步: 启动/重启服务..."
  remote "cd '${DEPLOY_PATH}' && bash scripts/stack.sh server-up -d 2>&1"

  info "第3步: 等待服务就绪..."
  sleep 5
  server_status

  info "=== 服务器全量重启完成 ==="
  echo ""
  echo "  Web: http://${DEPLOY_HOST}:40005/ai/"
}

# --- 只重启基础服务 ---
server_restart_base() {
  info "=== 重启基础服务（数据库/中间件/第三方依赖）==="
  remote "echo ok" >/dev/null || { error "SSH 连接失败"; exit 1; }

  local base_services="postgres redis minio pdf2zh-api"

  # 检测是否为 speech profile
  local has_speech
  has_speech=$(remote "cd '${DEPLOY_PATH}' && grep -q 'speech' .env 2>/dev/null && echo 1 || echo 0" 2>/dev/null || echo 0)
  if [[ "$has_speech" == "1" ]]; then
    base_services="$base_services speech-api"
  fi

  # 检测是否为 knowflow profile
  local has_knowflow
  has_knowflow=$(remote "cd '${DEPLOY_PATH}' && (grep -q 'knowflow' .env 2>/dev/null || grep -q 'STACK_PROFILES' .env 2>/dev/null) && echo 1 || echo 0" 2>/dev/null || echo 0)
  if [[ "$has_knowflow" == "1" ]]; then
    base_services="$base_services knowflow-mysql knowflow-infinity knowflow-gotenberg ragflow knowflow-backend"
  fi

  info "启动基础服务: $base_services"
  remote "cd '${DEPLOY_PATH}' && bash scripts/stack.sh server-up -d $base_services 2>&1"

  info "等待关键服务就绪..."
  wait_service_healthy "postgres" "pg_isready -U platform" 30 "PostgreSQL" || true
  wait_service_healthy "redis" "redis-cli ping | grep -q PONG" 15 "Redis" || true
  wait_service_healthy "minio" "curl -sf http://127.0.0.1:9000/minio/health/live" 20 "MinIO" || true

  if [[ "$has_knowflow" == "1" ]]; then
    wait_service_healthy "knowflow-mysql" "mysqladmin ping -uroot -pinfini_rag_flow" 30 "KnowFlow MySQL" || true
    wait_service_healthy "ragflow" "curl -sf http://127.0.0.1:80" 120 "RAGFlow" || true
  fi

  info "基础服务就绪"
}

# --- 服务器状态指示灯 ---
server_status() {
  info "=== 服务器服务状态（${DEPLOY_HOST}）==="
  echo ""

  echo -e "${BOLD}--- 基础服务 ---${NC}"
  check_container "postgres" "PostgreSQL" "pg_isready -U platform"
  check_container "redis" "Redis" 'redis-cli -a "$REDIS_PASSWORD" ping | grep -q PONG'
  check_container "minio" "MinIO" "curl -sf http://127.0.0.1:9000/minio/health/live"
  check_container "pdf2zh-api" "PDF2ZH" ""

  echo ""
  echo -e "${BOLD}--- 平台服务 ---${NC}"
  check_container "api" "API" ""
  check_container "frontend" "Frontend" ""
  check_container "worker" "Worker" ""

  echo ""
  echo -e "${BOLD}--- KnowFlow/RAGFlow ---${NC}"
  check_container "ragflow-mysql" "KF-MySQL" "mysqladmin ping -uroot -pinfini_rag_flow"
  check_container "ragflow-infinity" "Infinity" ""
  check_container "knowflow-gotenberg" "Gotenberg" ""
  check_container "ragflow-server" "RAGFlow" "curl -fsS http://127.0.0.1/v1/system/config > /dev/null"
  check_container "knowflow-backend" "KnowFlow" ""

  echo ""
  info "服务器 Web: http://${DEPLOY_HOST}:40005/ai/"
}

# --- 构建镜像 ---
server_build() {
  info "=== 服务器构建镜像 ==="
  remote "echo ok" >/dev/null || { error "SSH 连接失败"; exit 1; }

  local profiles
  profiles=$(remote "cd '${DEPLOY_PATH}' && grep -l knowflow .env 2>/dev/null || true")
  if [[ -n "$profiles" ]]; then
    remote "cd '${DEPLOY_PATH}' && bash scripts/stack.sh build --profile knowflow --profile speech 2>&1"
  else
    remote "cd '${DEPLOY_PATH}' && bash scripts/stack.sh build 2>&1"
  fi
  info "镜像构建完成"
}

# --- 查看日志 ---
server_logs() {
  local svc="${1:-}"
  remote "echo ok" >/dev/null || { error "SSH 连接失败"; exit 1; }
  if [[ -n "$svc" ]]; then
    remote "cd '${DEPLOY_PATH}' && bash scripts/stack.sh logs $svc"
  else
    info "查看所有服务日志（Ctrl+C 退出）..."
    remote "cd '${DEPLOY_PATH}' && bash scripts/stack.sh logs"
  fi
}

# --- 拉取最新代码并重启（无编译）---
server_pull_and_restart() {
  info "=== 拉取代码并重启服务 ==="
  remote "echo ok" >/dev/null || { error "SSH 连接失败"; exit 1; }

  info "拉取最新代码..."
  remote "cd '${DEPLOY_PATH}' && git pull --ff-only 2>&1"

  info "重启 API 和 Worker..."
  remote "cd '${DEPLOY_PATH}' && docker restart \$(docker ps -q -f name=api) \$(docker ps -q -f name=worker) 2>/dev/null || true"

  info "代码已同步，API/Worker 已重启"
  info "如需含编译的全量重启: ./dev.sh server restart"
}

# --- main ---
main() {
  local cmd="${1:-}"
  shift || true

  case "$cmd" in
    restart)
      case "${1:-}" in
        --base)
          server_restart_base
          ;;
        --service)
          local svc="${2:-}"
          [[ -z "$svc" ]] && { error "请指定服务名: --service <名称>"; exit 1; }
          remote "cd '${DEPLOY_PATH}' && bash scripts/stack.sh server-up -d $svc 2>&1"
          info "服务 $svc 已重启"
          ;;
        "")
          server_restart_all
          ;;
        *)
          error "未知选项: $1"; usage; exit 1
          ;;
      esac
      ;;
    status)
      server_status
      ;;
    build)
      server_build
      ;;
    logs)
      server_logs "${1:-}"
      ;;
    pull)
      server_pull_and_restart
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
