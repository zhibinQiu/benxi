#!/usr/bin/env bash
# 语音转写栈（FunASR）— 使用统一 compose profile speech
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}[speech-setup]${NC} $*"; }
warn() { echo -e "${YELLOW}[speech-setup]${NC} $*"; }

require_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "未找到: $1"; exit 1; }; }
require_cmd docker

MODELS_DIR="${SPEECH_MODELS_DIR:-$ROOT/data/speech-models}"
mkdir -p "$MODELS_DIR"
export DATA_ROOT="${DATA_ROOT:-$ROOT/data}"

info "模型目录: $MODELS_DIR（compose 卷 data/speech-models）"
info "构建并启动 speech-api profile …"
bash "$ROOT/scripts/stack.sh" build --profile speech
bash "$ROOT/scripts/stack.sh" up --profile speech

info "等待 speech-api（首次下载 ModelScope 模型，约 5–15 分钟）…"
for i in $(seq 1 90); do
  if docker compose -p zhitan exec -T speech-api python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health')" 2>/dev/null; then
    info "speech-api 已就绪（容器内网 http://speech-api:8765）"
    break
  fi
  sleep 10
done

warn "日志: docker compose -p zhitan logs -f speech-api"
warn "开发栈默认 SPEECH_SERVICE_URL=http://host.docker.internal:8765，生产为 http://speech-api:8765"

cat <<EOF

${GREEN}=== 语音栈 ===${NC}
  启动完整栈: bash scripts/stack.sh up --profile speech
  平台 .env: DEEPSEEK_API_KEY=sk-...（会议总结）

EOF
