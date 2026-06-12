#!/usr/bin/env bash
# 绿叶 AI 办公系统 — 统一 Docker 栈（仓库根 compose.yaml）
#
#   bash scripts/stack.sh build              # 构建自有镜像（core）
#   bash scripts/stack.sh build --profile knowflow --profile speech
#   bash scripts/stack.sh up                   # 启动 core（仅对外 FRONTEND_PORT）
#   bash scripts/stack.sh up --profile knowflow --profile speech
#   bash scripts/stack.sh dev-up               # 开发：挂载源码 + API reload
#   bash scripts/stack.sh down
#   bash scripts/stack.sh save                 # 导出镜像到 images/
#   bash scripts/stack.sh load images/*.tar.gz # 服务器导入
#   bash scripts/stack.sh backup | restore
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
info()  { echo -e "${GREEN}[stack]${NC} $*"; }
warn()  { echo -e "${YELLOW}[stack]${NC} $*"; }
error() { echo -e "${RED}[stack]${NC} $*" >&2; }

# shellcheck source=lib/version.sh
source "$ROOT/scripts/lib/version.sh"
# shellcheck source=lib/branding.sh
source "$ROOT/scripts/lib/branding.sh"
ZHITAN_VERSION="${ZHITAN_VERSION:-$(read_repo_version "$ROOT")}"
DATA_ROOT="${DATA_ROOT:-./data}"
IMAGES_DIR="${IMAGES_DIR:-./images}"
COMPOSE_PROFILES_EXTRA=()
COMPOSE_DEV=0

load_env() {
  if [[ ! -f .env ]]; then
    if [[ -f platform/.env ]]; then
      bash "$ROOT/scripts/setup-stack-env.sh"
    else
      warn "未找到 .env，执行: cp .env.stack.example .env"
    fi
  fi
  if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
  fi
  ZHITAN_VERSION="${ZHITAN_VERSION:-$(read_repo_version "$ROOT")}"
  export ZHITAN_VERSION DATA_ROOT COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-zhitan}"
  mkdir -p "$DATA_ROOT" "$IMAGES_DIR" backups
}

default_profiles() {
  if [[ ${#COMPOSE_PROFILES_EXTRA[@]} -gt 0 ]]; then
    return
  fi
  local raw="${STACK_PROFILES:-}"
  if [[ -n "$raw" ]]; then
    local p
    for p in $raw; do
      COMPOSE_PROFILES_EXTRA+=("$p")
    done
  fi
}

use_mirror_compose() {
  [[ "${STACK_USE_MIRROR:-1}" == 1 ]]
}

compose_cmd() {
  local -a args=(compose -f compose.yaml)
  if use_mirror_compose && [[ -f compose.mirror.yaml ]]; then
    args+=(-f compose.mirror.yaml)
  fi
  if [[ -f deploy/knowflow.yml ]]; then
    args+=(-f deploy/knowflow.yml)
    if use_mirror_compose && [[ -f deploy/knowflow.mirror.yaml ]]; then
      args+=(-f deploy/knowflow.mirror.yaml)
    fi
  fi
  if [[ "$COMPOSE_DEV" == 1 ]]; then
    args+=(-f compose.dev.yaml)
  fi
  if [[ "${EXPOSE_DEPS:-0}" == 1 ]] && [[ -f compose.expose-deps.yaml ]]; then
    args+=(-f compose.expose-deps.yaml)
  fi
  if [[ ${#COMPOSE_PROFILES_EXTRA[@]} -gt 0 ]]; then
    local p
    for p in "${COMPOSE_PROFILES_EXTRA[@]}"; do
      args+=(--profile "$p")
    done
  fi
  docker "${args[@]}" "$@"
}

detect_arch() {
  case "$(uname -m)" in
    x86_64) echo amd64 ;;
    aarch64|arm64) echo arm64 ;;
    *) error "不支持的架构: $(uname -m)"; exit 1 ;;
  esac
}

image_list() {
  local with_infra="${STACK_SAVE_INFRA:-1}"
  local -a imgs=(
    "zhitan-api:${ZHITAN_VERSION}"
    "zhitan-frontend:${ZHITAN_VERSION}"
    "zhitan-pdf2zh:${ZHITAN_VERSION}"
  )
  local has_speech=0 has_kf=0
  for p in "${COMPOSE_PROFILES_EXTRA[@]}"; do
    [[ "$p" == speech ]] && has_speech=1
    [[ "$p" == knowflow ]] && has_kf=1
  done
  [[ "$has_speech" == 1 ]] && imgs+=("zhitan-speech:${ZHITAN_VERSION}")
  if [[ "$has_kf" == 1 ]]; then
    if [[ -n "${RAGFLOW_IMAGE:-}" ]]; then
      imgs+=("${RAGFLOW_IMAGE}")
    else
      imgs+=("knowflow-ragflow:source")
    fi
    if [[ -n "${KNOWFLOW_SERVER_IMAGE:-}" ]]; then
      imgs+=("${KNOWFLOW_SERVER_IMAGE}")
    else
      imgs+=("knowflow-server:source")
    fi
  fi
  if [[ "$with_infra" == 1 ]]; then
    imgs+=(
      "${POSTGRES_IMAGE:-postgres:16-alpine}"
      "${REDIS_IMAGE:-redis:7-alpine}"
      "${MINIO_IMAGE:-minio/minio:latest}"
    )
    if [[ "$has_kf" == 1 ]]; then
      imgs+=(
        "mysql:8.0.39"
        "infiniflow/infinity:${INFINITY_VERSION:-v0.6.0-dev5}"
        "gotenberg/gotenberg:8"
      )
    fi
  fi
  printf '%s\n' "${imgs[@]}"
}

cmd_build() {
  load_env
  # build 默认仅核心三镜像；要 knowflow/speech 请显式 --profile 或先 stack.sh build --profile knowflow
  if [[ ${#COMPOSE_PROFILES_EXTRA[@]} -eq 0 ]]; then
    info "构建核心镜像（api / worker / frontend / pdf2zh-api）..."
    compose_cmd build --parallel api worker frontend pdf2zh-api "$@"
    return
  fi
  local -a targets=()
  local p
  for p in "${COMPOSE_PROFILES_EXTRA[@]}"; do
    case "$p" in
      speech) targets+=(speech-api) ;;
      knowflow) targets+=(ragflow knowflow-backend) ;;
      *) warn "未知 profile: $p" ;;
    esac
  done
  if [[ ${#targets[@]} -eq 0 ]]; then
    error "无有效 profile 可构建"
    exit 1
  fi
  info "构建镜像 ZHITAN_VERSION=${ZHITAN_VERSION} profiles=${COMPOSE_PROFILES_EXTRA[*]} → ${targets[*]}"
  compose_cmd build --parallel "${targets[@]}" "$@"
}

cmd_pull() {
  load_env
  default_profiles
  info "拉取基础镜像（postgres/redis/minio 等）..."
  compose_cmd pull postgres redis minio 2>/dev/null || true
  if [[ " ${COMPOSE_PROFILES_EXTRA[*]} " == *" knowflow "* ]]; then
    compose_cmd pull knowflow-mysql knowflow-infinity knowflow-gotenberg 2>/dev/null || true
  fi
}

cmd_up() {
  load_env
  default_profiles
  # 服务器 load 镜像后勿触发本地 build（无 third_party 源码时）
  compose_cmd up -d --no-build "$@"
  local port="${FRONTEND_PORT:-40005}"
  local host="${DEPLOY_HOST:-127.0.0.1}"
  local app_name
  app_name="$(read_platform_app_name "$ROOT")"
  cat <<EOF

${GREEN}=== ${app_name} 栈已启动 ===${NC}
  Web（唯一推荐入口）: http://${host}:${port}/ai/
  容器内 API:          http://api:8000
  数据目录:            ${DATA_ROOT}

EOF
}

cmd_dev_up() {
  COMPOSE_DEV=1
  export VITE_DEV_API_TARGET="${VITE_DEV_API_TARGET:-http://api:8000}"
  load_env
  default_profiles
  info "开发模式：API --reload + 前端 Vite（挂载源码）"
  compose_cmd up -d --no-build "$@"
  local port="${FRONTEND_PORT:-40005}"
  local app_name
  app_name="$(read_platform_app_name "$ROOT")"
  cat <<EOF

${GREEN}=== ${app_name} 开发栈已启动 ===${NC}
  Web:     http://127.0.0.1:${port}/ai/
  API:     http://127.0.0.1:${STACK_DEV_API_PORT:-18000}（开发模式浏览器直连）
  热更新:  改 platform/app、platform-frontend → 自动生效
  Worker:  改 workers 后执行: docker compose -p ${COMPOSE_PROJECT_NAME:-zhitan} restart worker
  生产式:  bash scripts/stack.sh up（需先 build）

EOF
}

cmd_down() {
  load_env
  compose_cmd down "$@"
}

cmd_logs() {
  load_env
  default_profiles
  compose_cmd logs -f --tail=200 "$@"
}

cmd_init_env() {
  bash "$ROOT/scripts/setup-stack-env.sh"
}

cmd_save() {
  load_env
  default_profiles
  local arch out
  arch="$(detect_arch)"
  out="${1:-${IMAGES_DIR}/zhitan-${ZHITAN_VERSION}-${arch}.tar.gz}"
  mkdir -p "$(dirname "$out")"
  local -a imgs=()
  while IFS= read -r line; do
    [[ -n "$line" ]] && imgs+=("$line")
  done < <(image_list | sort -u)
  info "导出 ${#imgs[@]} 个镜像 → ${out}"
  docker save "${imgs[@]}" | gzip -c >"$out"
  info "完成: $(du -h "$out" | awk '{print $1}')"
  echo "$out"
}

cmd_load() {
  local f="${1:?用法: stack.sh load images/zhitan-3.9.2-amd64.tar.gz}"
  [[ -f "$f" ]] || { error "文件不存在: $f"; exit 1; }
  info "导入 $f ..."
  gzip -dc "$f" | docker load
  info "导入完成"
}

cmd_backup() {
  load_env
  local stamp dest
  stamp="$(date +%Y%m%d_%H%M%S)"
  dest="backups/${stamp}"
  mkdir -p "$dest"
  info "备份 PostgreSQL → ${dest}/postgres.sql.gz"
  compose_cmd exec -T postgres pg_dump -U "${POSTGRES_USER:-platform}" "${POSTGRES_DB:-platform}" \
    | gzip -c >"${dest}/postgres.sql.gz"
  if compose_cmd ps --status running 2>/dev/null | grep -q knowflow-mysql; then
    info "备份 KnowFlow MySQL → ${dest}/knowflow-mysql.sql.gz"
    compose_cmd exec -T knowflow-mysql mysqldump -uroot -p"${MYSQL_PASSWORD:-infini_rag_flow}" --all-databases \
      | gzip -c >"${dest}/knowflow-mysql.sql.gz" 2>/dev/null || warn "MySQL 备份跳过"
  fi
  info "打包 MinIO 数据 → ${dest}/minio.tar.gz"
  tar -czf "${dest}/minio.tar.gz" -C "$DATA_ROOT" minio 2>/dev/null || warn "minio 目录为空"
  cat >"${dest}/manifest.json" <<EOF
{"version":"${ZHITAN_VERSION}","time":"${stamp}","data_root":"${DATA_ROOT}"}
EOF
  info "备份完成: ${dest}"
}

cmd_restore() {
  local dest="${1:?用法: stack.sh restore backups/20260101_120000}"
  load_env
  [[ -d "$dest" ]] || { error "目录不存在: $dest"; exit 1; }
  warn "将覆盖 ${DATA_ROOT} 中部分数据，10 秒内 Ctrl+C 取消"
  sleep 3
  if [[ -f "${dest}/postgres.sql.gz" ]]; then
    if [[ ! -f "${dest}/minio.tar.gz" ]]; then
      warn "备份含 PostgreSQL 但缺少 minio.tar.gz，恢复后文档元数据将与对象存储不一致"
    fi
    info "恢复 PostgreSQL"
    gzip -dc "${dest}/postgres.sql.gz" | compose_cmd exec -T postgres psql -U "${POSTGRES_USER:-platform}" -d "${POSTGRES_DB:-platform}"
  fi
  if [[ -f "${dest}/minio.tar.gz" ]]; then
    info "恢复 MinIO"
    mkdir -p "$DATA_ROOT/minio"
    tar -xzf "${dest}/minio.tar.gz" -C "$DATA_ROOT"
  fi
  info "恢复完成，请 stack.sh up"
}

cmd_ps() {
  load_env
  compose_cmd ps "$@"
}

usage() {
  cat <<'EOF'
用法: bash scripts/stack.sh <命令> [选项]

命令:
  build [服务名...]     构建镜像（可加 --profile knowflow --profile speech）
  up [-d]               启动栈
  dev-up                开发模式（挂载源码）
  down                  停止
  save [输出文件]       docker save → images/zhitan-<ver>-<arch>.tar.gz
  load <文件>           docker load（服务器）
  pull                  拉取基础镜像（在线）
  backup                逻辑备份到 backups/
  restore <目录>        从 backup 目录恢复
  ps                    查看状态
  logs [服务名]         查看日志
  init-env              生成 .env（合并 platform/.env）

环境变量:
  EXPOSE_DEPS=1         叠加 compose.expose-deps.yaml（远程依赖开发）
  STACK_USE_MIRROR=1    叠加 compose.mirror.yaml（默认开启）
  COMPOSE_PROJECT_NAME  默认 zhitan；远程依赖栈可用 lvye

示例:
  bash scripts/stack.sh build --profile speech
  bash scripts/stack.sh up --profile knowflow --profile speech
  bash scripts/stack.sh save
  rsync -avz images/ user@server:/opt/zhitan/images/
  ssh user@server 'cd /opt/zhitan && bash scripts/stack.sh load images/zhitan-3.9.2-amd64.tar.gz && bash scripts/stack.sh up'
EOF
}

main() {
  local cmd="" 
  local -a rest=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --profile)
        COMPOSE_PROFILES_EXTRA+=("$2")
        shift 2
        ;;
      -h|--help|help)
        usage
        exit 0
        ;;
      *)
        if [[ -z "$cmd" ]]; then
          cmd="$1"
          shift
        else
          rest+=("$1")
          shift
        fi
        ;;
    esac
  done
  if [[ ${#rest[@]} -gt 0 ]]; then
    set -- "${rest[@]}"
  else
    set --
  fi

  case "$cmd" in
    build)   cmd_build "$@" ;;
    up)      cmd_up "$@" ;;
    dev-up)  cmd_dev_up "$@" ;;
    down)    cmd_down "$@" ;;
    save)    cmd_save "$@" ;;
    load)    cmd_load "$@" ;;
    pull)    cmd_pull "$@" ;;
    backup)  cmd_backup "$@" ;;
    restore) cmd_restore "$@" ;;
    ps)      cmd_ps "$@" ;;
    logs)    cmd_logs "$@" ;;
    init-env) cmd_init_env "$@" ;;
    ""|help|-h|--help) usage ;;
    *) error "未知命令: $cmd"; usage; exit 1 ;;
  esac
}

main "$@"
