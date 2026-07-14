#!/usr/bin/env bash
# 数据目录迁移脚本：将 third_party/data 迁移到项目根目录 ./data
#
# 用法: bash scripts/migrate-data-dir.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[migrate-data]${NC} $*"; }
warn()  { echo -e "${YELLOW}[migrate-data]${NC} $*"; }

OLD_DATA_DIR="$ROOT/third_party/data"
NEW_DATA_DIR="$ROOT/data"

if [[ -d "$NEW_DATA_DIR" ]]; then
  info "目标数据目录 $NEW_DATA_DIR 已存在，跳过迁移。"
  exit 0
fi

if [[ ! -d "$OLD_DATA_DIR" ]]; then
  info "旧数据目录 $OLD_DATA_DIR 不存在，无需迁移。"
  mkdir -p "$NEW_DATA_DIR"
  info "已创建空数据目录 $NEW_DATA_DIR"
  exit 0
fi

info "迁移数据目录: $OLD_DATA_DIR -> $NEW_DATA_DIR"

# 创建软链接兼容旧的引用
ln -sf ../data "$ROOT/third_party/data"
info "已创建软链接: third_party/data -> ../data"

# 在 data 目录就地创建，用 inode 相同的 rsync 方式避免大文件拷贝
# 使用 mv 移到本目录
cd "$ROOT"
mv "third_party/data" "data"

# 重建软链接
ln -sf ../data "third_party/data"

info "迁移完成。数据目录: $NEW_DATA_DIR"
info "软链接已保留: third_party/data -> ../data"
echo ""
info "运行 docker 前请重新生成 .env: bash scripts/setup-stack-env.sh"
