#!/usr/bin/env bash
# 企业 AI 知识库平台 — 开发入口（转发至 scripts/dev.sh）
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/dev.sh" "$@"
