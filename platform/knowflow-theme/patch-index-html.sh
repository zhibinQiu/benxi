#!/usr/bin/env sh
# 容器启动时向 dist/index.html 注入白标脚本（sub_filter 对部分静态响应不可靠）
set -e
INDEX="/ragflow/web/dist/index.html"
MARKER="platform-branding.js"
INJECT='<link rel="stylesheet" href="/platform-branding.css"><script src="/platform-branding.js"></script>'
if [ ! -f "$INDEX" ]; then
  exit 0
fi
if grep -q "$MARKER" "$INDEX" 2>/dev/null; then
  exit 0
fi
# macOS/BSD sed 与 GNU sed 兼容
if sed --version >/dev/null 2>&1; then
  sed -i "s|</head>|${INJECT}</head>|i" "$INDEX"
else
  sed -i '' "s|</head>|${INJECT}</head>|i" "$INDEX"
fi
