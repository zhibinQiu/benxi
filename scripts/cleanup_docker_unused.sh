#!/usr/bin/env bash
# 清理与本项目无关的已停止容器、KnowFlow 旧 amd64 镜像及悬空层（保留 platform / knowflow 运行中栈）
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
info() { echo -e "${GREEN}[cleanup]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }

KEEP_REGEX='^(platform-|ragflow-|knowflow-)'

info "停止并删除已退出的非智碳/KnowFlow 容器（如 dify）..."
while IFS= read -r id; do
  [[ -z "$id" ]] && continue
  name=$(docker inspect -f '{{.Name}}' "$id" 2>/dev/null | sed 's/^\///')
  if [[ "$name" =~ $KEEP_REGEX ]]; then
    continue
  fi
  info "  删除容器 $name ($id)"
  docker rm -f "$id" >/dev/null 2>&1 || true
done < <(docker ps -aq --filter 'status=exited' 2>/dev/null || true)

info "删除 KnowFlow 旧预构建镜像（仅按仓库名+tag，不删 knowflow-*:source / infiniflow/ragflow_deps）..."
while read -r ref; do
  [[ -z "$ref" ]] && continue
  case "$ref" in
    knowflow-ragflow:source|knowflow-server:source|infiniflow/ragflow_deps:latest) continue ;;
  esac
  if docker ps -a --filter "ancestor=$ref" -q 2>/dev/null | grep -q .; then
    warn "  跳过（仍有容器）: $ref"
    continue
  fi
  warn "  docker rmi $ref"
  docker rmi "$ref" 2>/dev/null || true
done < <(docker images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null | grep -E '^(zxwei/|docker\.1ms\.run/zxwei/)' || true)

info "清理悬空镜像与构建缓存（不删正在使用的层）..."
docker image prune -f >/dev/null 2>&1 || true
docker builder prune -f --filter 'until=24h' >/dev/null 2>&1 || true

info "完成。当前容器："
docker ps -a --format '  {{.Names}}\t{{.Status}}' 2>/dev/null | head -25 || true
