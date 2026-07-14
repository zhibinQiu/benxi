#!/usr/bin/env bash
# 服务器数据定期备份脚本
# 在服务器上通过 cron 定时执行，备份到服务器本地 backups/ 目录
#
# 安装到 cron（每周日凌晨 3 点备份，保留最近 30 天）:
#   crontab -e
#   0 3 * * 0 /root/qzb/benxi/scripts/server-backup.sh
#
# 手动执行:
#   bash scripts/server-backup.sh
#   bash scripts/server-backup.sh --keep 60  # 保留 60 天
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
info()  { echo -e "${GREEN}[backup]${NC} $*"; }
warn()  { echo -e "${YELLOW}[backup]${NC} $*"; }
error() { echo -e "${RED}[backup]${NC} $*" >&2; }

KEEP_DAYS=30

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --keep) KEEP_DAYS="$2"; shift 2 ;;
      -h|--help)
        sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
        exit 0
        ;;
      *) error "未知参数: $1"; shift ;;
    esac
  done
}

main() {
  parse_args "$@"

  # 必要性检查：确认 docker 和 stack.sh 可用
  command -v docker >/dev/null 2>&1 || { error "docker 不可用"; exit 1; }
  [[ -f scripts/stack.sh ]] || { error "未找到 scripts/stack.sh，请在项目根目录执行"; exit 1; }
  [[ -f .env ]] || { warn "未找到 .env，部分备份可能失败"; }

  info "===== 开始数据备份 ====="
  info "保留最近 ${KEEP_DAYS} 天的备份"

  # 1. 执行 stack.sh backup
  bash scripts/stack.sh backup

  # 2. 清理过期备份
  local backups_dir="$ROOT/backups"
  if [[ -d "$backups_dir" ]]; then
    local count
    count=$(find "$backups_dir" -maxdepth 1 -type d -name '2*' | wc -l)
    info "清理 ${KEEP_DAYS} 天前的备份（当前 ${count} 份）…"
    find "$backups_dir" -maxdepth 1 -type d -name '2*' -mtime "+${KEEP_DAYS}" -exec rm -rf {} \; -print
  fi

  # 3. 输出最近备份信息
  local latest
  latest=$(ls -dt "$backups_dir"/2* 2>/dev/null | head -1)
  if [[ -n "$latest" ]]; then
    info "最新备份: $latest"
    ls -lh "$latest/"
  fi

  info "===== 备份完成 ====="
}

main "$@"
