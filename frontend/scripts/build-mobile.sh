#!/bin/bash
# ============================================
# 移动端构建脚本 — 本析知识平台
# 用法:
#   ./scripts/build-mobile.sh android   # 构建并打开 Android Studio
#   ./scripts/build-mobile.sh ios       # 构建并打开 Xcode（需 macOS + Xcode）
#   ./scripts/build-mobile.sh           # 仅构建 Web 资源
# ============================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../frontend" && pwd)"
cd "$PROJECT_DIR"

echo "========================================"
echo " 本析 — 移动端构建"
echo "========================================"
echo ""

# 1. 构建移动端 Web 资源
echo "→ 构建移动端 Web 资源..."
npm run build:mobile
echo "  ✓ 构建完成 (dist-mobile/)"
echo ""

# 2. 配置 API 后端地址（可选）
if [ -n "${VITE_MOBILE_API_BASE:-}" ]; then
  echo "→ 使用自定义 API 地址: $VITE_MOBILE_API_BASE"
  # 重新构建
  VITE_MOBILE_API_BASE="$VITE_MOBILE_API_BASE" npm run build:mobile
  echo "  ✓ 已重新构建"
fi

# 3. 同步到各平台
echo "→ 同步到 Capacitor 平台..."
npx cap copy 2>&1
echo "  ✓ 资源已同步到 Android / iOS"
echo ""

PLATFORM="${1:-}"

if [ "$PLATFORM" = "android" ]; then
  echo "→ 打开 Android Studio..."
  npx cap open android
  echo ""
  echo "提示: 在 Android Studio 中点击 Run 即可编译 APK"
elif [ "$PLATFORM" = "ios" ]; then
  echo "→ 打开 Xcode..."
  npx cap open ios
  echo ""
  echo "提示: 在 Xcode 中选择目标设备后点击 Run 即可编译 IPA"
else
  echo "========================================"
  echo " 构建完成！"
  echo ""
  echo "下一步:"
  echo "  ./scripts/build-mobile.sh android   → 打开 Android Studio 编译 APK"
  echo "  ./scripts/build-mobile.sh ios       → 打开 Xcode 编译 IPA"
  echo ""
  echo "环境变量:"
  echo "  VITE_MOBILE_API_BASE= 指定后端 API 地址（例: https://api.example.com）"
  echo "========================================"
fi
