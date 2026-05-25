#!/usr/bin/env bash
# KnowFlow 阶段 2–4 集成冒烟（需平台 API + KnowFlow 栈运行）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="$ROOT/platform"
API="${PLATFORM_API_URL:-http://127.0.0.1:8000}"

cd "$PLATFORM"
source .venv/bin/activate 2>/dev/null || true

echo "=== 单元测试 ==="
pytest tests/test_ragflow_identity.py tests/test_ragflow_provision.py tests/test_ragflow_sync.py -q

echo "=== HTTP 栈检查 ==="
bash "$ROOT/scripts/check_knowflow.sh"

if [[ ! -f "$PLATFORM/.env" ]] || ! grep -q '^KNOWFLOW_ENABLED=true' "$PLATFORM/.env" 2>/dev/null; then
  if [[ -f "$PLATFORM/knowflow.env" ]]; then
    export KNOWFLOW_ENABLED=true
  else
    echo "[skip] KNOWFLOW_ENABLED 未开启，跳过 embed-session 实网测试"
    exit 0
  fi
fi

TOKEN=$(python3 - <<'PY' 2>/dev/null || true
import os, httpx
from pathlib import Path
env = {}
for line in Path(".env").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
u, p = env.get("BOOTSTRAP_ADMIN_USERNAME", "admin"), env.get("BOOTSTRAP_ADMIN_PASSWORD", "admin123")
r = httpx.post("http://127.0.0.1:8000/api/v1/auth/login", json={"username": u, "password": p}, timeout=10)
if r.status_code == 200 and r.json().get("code") == 0:
    print(r.json()["data"]["access_token"])
PY
)
if [[ -z "${TOKEN:-}" ]]; then
  echo "[warn] 无法获取平台 token，跳过 embed-session"
  exit 0
fi

echo "=== embed-session SSO ==="
BODY=$(curl -sf -H "Authorization: Bearer $TOKEN" "$API/api/v1/rag/embed-session")
echo "$BODY" | python3 -c "
import json,sys
d=json.load(sys.stdin).get('data',{})
sso=d.get('sso',{})
assert d.get('integration_phase')>=2, d
print('phase', d.get('integration_phase'))
print('sso.ready', sso.get('ready'))
print('synced', d.get('synced_documents'))
if not sso.get('ready'):
    raise SystemExit('SSO 未就绪: '+sso.get('message',''))
print('[ok] embed-session SSO')
"
