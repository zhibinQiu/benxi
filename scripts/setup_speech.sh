#!/usr/bin/env bash
# 首次启动本地语音转写栈（FunASR Docker）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="$ROOT/platform"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}[speech-setup]${NC} $*"; }
warn() { echo -e "${YELLOW}[speech-setup]${NC} $*"; }

require_cmd docker

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODELS_DIR="${SPEECH_MODELS_DIR:-$ROOT/.run/speech-models}"
mkdir -p "$MODELS_DIR"
export SPEECH_MODELS_DIR="$MODELS_DIR"

cd "$PLATFORM"

info "模型目录: $MODELS_DIR"
info "构建并启动 speech-api（FunASR）..."
docker compose -f docker-compose.speech.yml up -d --build

info "等待 speech-api 健康检查（首次会下载 ModelScope 模型，约 5–15 分钟）..."
for i in $(seq 1 90); do
  if curl -sf "http://127.0.0.1:8765/health" >/dev/null 2>&1; then
    info "speech-api 已就绪: http://127.0.0.1:8765"
    curl -sf "http://127.0.0.1:8765/meta" | head -c 500 || true
    echo ""
    break
  fi
  sleep 10
done

warn "若 health 未通过，查看日志: docker compose -f docker-compose.speech.yml logs -f speech-api"

cat <<EOF

${GREEN}=== 语音栈配置提示 ===${NC}

  模型缓存（项目内）:
    $MODELS_DIR

  转写（Docker FunASR）:
    SPEECH_SERVICE_URL=http://127.0.0.1:8765
    SPEECH_MODELS_DIR=$MODELS_DIR

  说话人分离: 内置 CAM++，无需 HF_TOKEN

  总结（DeepSeek）:
    platform/.env 设置 DEEPSEEK_API_KEY=sk-...
    或沿用 ~/.config/pdf2zh/config.v3.toml 中的 deepseek_api_key

  启动平台: bash scripts/start_platform.sh speech

EOF
