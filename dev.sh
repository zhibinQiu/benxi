#!/usr/bin/env bash
# 绿叶 AI 办公系统 — 开发入口（转发至 scripts/dev.sh）
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/dev.sh" "$@"
