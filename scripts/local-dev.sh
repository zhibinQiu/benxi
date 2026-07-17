#!/usr/bin/env bash
# 本机 conda 开发：API :8000 + Vite :40005 + 按需 Celery Worker
# 由 ./dev.sh local 调用，勿直接执行。
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck source=scripts/lib/branding.sh
source "$ROOT/scripts/lib/branding.sh"
# shellcheck source=scripts/lib/version.sh
source "$ROOT/scripts/lib/version.sh"

RUN_DIR="$ROOT/.run"
LOG_DIR="$RUN_DIR/logs"
PLATFORM_DIR="$ROOT/backend"
ENV_FILE="$PLATFORM_DIR/.env"
HOST_BIND="${LOCAL_DEV_HOST:-127.0.0.1}"
API_PORT="${LOCAL_DEV_API_PORT:-8000}"
WEB_PORT="${LOCAL_DEV_WEB_PORT:-40005}"
LOCAL_DEV_CONDA_ENV="${LOCAL_DEV_CONDA_ENV:-pdf2zh}"

# 直接调用 env 内 python；本机 conda run 可能误用 /usr/local 或 Homebrew 解释器
resolve_conda_env_python() {
  if [[ -n "${LOCAL_DEV_CONDA_PYTHON:-}" && -x "${LOCAL_DEV_CONDA_PYTHON}" ]]; then
    echo "${LOCAL_DEV_CONDA_PYTHON}"
    return 0
  fi
  local base env_py
  base="$(conda info --base 2>/dev/null || true)"
  env_py="${base}/envs/${LOCAL_DEV_CONDA_ENV}/bin/python"
  if [[ -x "$env_py" ]]; then
    echo "$env_py"
    return 0
  fi
  return 1
}

CONDA_ENV_PYTHON="$(resolve_conda_env_python || true)"
PYTHON_CMD=("${CONDA_ENV_PYTHON}")
UVICORN_CMD=("${CONDA_ENV_PYTHON}" -m uvicorn)
CELERY_CMD=("${CONDA_ENV_PYTHON}" -m celery)

init_paths() {
  mkdir -p "$LOG_DIR"
}

ensure_conda_env() {
  command -v conda >/dev/null 2>&1 || {
    echo "未找到 conda，请先安装/初始化 conda，并确认环境 ${LOCAL_DEV_CONDA_ENV} 可用。" >&2
    return 1
  }
  CONDA_ENV_PYTHON="$(resolve_conda_env_python)" || {
    echo "未找到 conda 环境 Python: ${LOCAL_DEV_CONDA_ENV}" >&2
    echo "请先创建环境，或设置 LOCAL_DEV_CONDA_PYTHON 指向可执行 python。" >&2
    return 1
  }
  PYTHON_CMD=("${CONDA_ENV_PYTHON}")
  UVICORN_CMD=("${CONDA_ENV_PYTHON}" -m uvicorn)
  CELERY_CMD=("${CONDA_ENV_PYTHON}" -m celery)
  "${CONDA_ENV_PYTHON}" -c 'import sys' >/dev/null 2>&1 || {
    echo "无法执行 conda 环境 Python: ${CONDA_ENV_PYTHON}" >&2
    return 1
  }
}

is_remote_deps() {
  [[ -f "$ENV_FILE" ]] && grep -q '^REMOTE_DEPS=1' "$ENV_FILE"
}

rotate_logs() {
  local f max_mb=50
  for f in "$LOG_DIR/platform-api.log" "$LOG_DIR/platform-frontend.log" "$LOG_DIR/platform-worker.log"; do
    [[ -f "$f" ]] || continue
    local size_mb
    size_mb="$(du -m "$f" | awk '{print $1}')"
    if [[ "${size_mb:-0}" -ge "$max_mb" ]]; then
      mv "$f" "${f%.log}.$(date +%Y%m%d%H%M%S).bak"
      : >"$f"
      echo "  已轮转过大日志: $(basename "$f")（原 ${size_mb}MB）"
    fi
  done
}

step() {
  echo "→ $*"
}

start_detached() {
  local logfile=$1
  shift
  if [[ "$(uname -s)" != "Darwin" ]] && command -v setsid >/dev/null 2>&1; then
    setsid "$@" >>"$logfile" 2>&1 </dev/null &
  else
    nohup "$@" >>"$logfile" 2>&1 </dev/null &
    disown -h 2>/dev/null || true
  fi
  echo $!
}

stop_local() {
  init_paths
  pkill -9 -f "uvicorn app.main:app --host" 2>/dev/null || true
  pkill -9 -f "celery -A workers.celery_app worker" 2>/dev/null || true
  pkill -9 -f "vite --host" 2>/dev/null || true
  pkill -9 -f "node.*vite.*${WEB_PORT}" 2>/dev/null || true
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti :"${API_PORT}" | xargs kill -9 2>/dev/null || true
    lsof -ti :"${WEB_PORT}" | xargs kill -9 2>/dev/null || true
  fi
  rm -f "$RUN_DIR/platform-api.pid" \
    "$RUN_DIR/platform-frontend.pid" \
    "$RUN_DIR/platform-worker.pid"
}

run_with_timeout() {
  local secs=$1
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "$secs" "$@" 2>/dev/null || echo 0
    return
  fi
  if command -v gtimeout >/dev/null 2>&1; then
    gtimeout "$secs" "$@" 2>/dev/null || echo 0
    return
  fi
  # macOS 无 timeout：后台运行，超时则终止
  "$@" 2>/dev/null &
  local pid=$!
  local i
  for i in $(seq 1 "$secs"); do
    if ! kill -0 "$pid" 2>/dev/null; then
      wait "$pid" 2>/dev/null || echo 0
      return
    fi
    sleep 1
  done
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  echo 0
}

remote_celery_worker_count() {
  run_with_timeout 15 env ENV_FILE="$ENV_FILE" PLATFORM="$PLATFORM_DIR" \
    "${PYTHON_CMD[@]}" - <<'PY' 2>/dev/null || echo 0
import os
import sys
from pathlib import Path

platform = Path(os.environ["PLATFORM"])
sys.path.insert(0, str(platform))

env_path = Path(os.environ["ENV_FILE"])
env = {}
for line in env_path.read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    env[k.strip()] = v.strip()

url = env.get("REDIS_URL") or env.get("CELERY_BROKER_URL") or ""
if not url:
    print(0)
    raise SystemExit
try:
    from workers.celery_app import celery_app

    celery_app.conf.broker_url = url
    insp = celery_app.control.inspect(timeout=3)
    ping = insp.ping() or {}
    print(len(ping))
except Exception:
    print(0)
PY
}

should_start_worker() {
  case "${START_LOCAL_WORKER:-auto}" in
    0|false|no|off) return 1 ;;
    1|true|yes|on) return 0 ;;
  esac
  local n
  n="$(remote_celery_worker_count)"
  [[ "${n:-0}" -eq 0 ]]
}

uses_local_postgres() {
  [[ -f "$ENV_FILE" ]] || return 1
  grep -E '^DATABASE_URL=.*@127\.0\.0\.1:' "$ENV_FILE" >/dev/null 2>&1
}

ensure_local_postgres() {
  uses_local_postgres || return 0
  local port="${LOCAL_POSTGRES_PORT:-5432}"
  if [[ -f "$ENV_FILE" ]]; then
    port="$(grep -E '^LOCAL_POSTGRES_PORT=' "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\r' || true)"
    port="${port:-5432}"
  fi
  if docker compose -f "$ROOT/configs/compose/compose.yaml" ps postgres 2>/dev/null | grep -q healthy; then
    return 0
  fi
  step "启动本机 PostgreSQL（:${port}）…"
  LOCAL_POSTGRES_PORT="$port" docker compose -f "$ROOT/configs/compose/compose.yaml" up -d postgres
  local i
  for i in $(seq 1 20); do
    if docker compose -f "$ROOT/configs/compose/compose.yaml" ps postgres 2>/dev/null | grep -q healthy; then
      echo "  本机 postgres 已就绪"
      return 0
    fi
    sleep 1
  done
  echo "本机 postgres 未在 20s 内就绪，请检查: docker compose -f configs/compose/compose.yaml logs postgres" >&2
  return 1
}

preflight_database() {
  ensure_local_postgres || return 1
  step "预检数据库连接（API 启动依赖，最多 3 次）…"
  local attempt ok=0
  for attempt in 1 2 3; do
    if run_with_timeout 20 env ENV_FILE="$ENV_FILE" PLATFORM="$PLATFORM_DIR" \
      "${PYTHON_CMD[@]}" - <<'PY'
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import psycopg2

env = {}
for line in Path(os.environ["ENV_FILE"]).read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    env[k.strip()] = v.strip()

url = env.get("DATABASE_URL", "")
if not url:
    print("未配置 DATABASE_URL", file=sys.stderr)
    raise SystemExit(1)

parsed = urlparse(url.replace("+psycopg2", ""))
conn = psycopg2.connect(
    host=parsed.hostname,
    port=parsed.port or 5432,
    user=parsed.username,
    password=parsed.password,
    dbname=(parsed.path or "/").lstrip("/"),
    connect_timeout=12,
)
cur = conn.cursor()
cur.execute("SELECT 1")
cur.fetchone()
conn.close()
PY
    then
      ok=1
      break
    fi
    echo "  第 ${attempt}/3 次失败，${attempt}＜3 时 5 秒后重试…"
    sleep 5
    if [[ "$ok" -ne 1 && "$attempt" -eq 2 && ! uses_local_postgres ]]; then
      local remote_host
      remote_host="$(grep -E '^REMOTE_HOST=' "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\r' || true)"
      remote_host="${remote_host:-172.19.134.45}"
      echo "  提示: 服务器 ${remote_host} Postgres 端口映射可能异常（40002），如持续连接失败请手动执行:"
      echo "    ssh root@${remote_host} 'cd /root/qzb/benxi && docker compose -f configs/compose/compose.yaml -f configs/compose/compose.server.yaml -f configs/compose/compose.expose-deps.yaml up -d postgres --force-recreate'"
    fi
  done
  if [[ "$ok" -ne 1 ]]; then
    echo ""
    echo "数据库无法连接 — API 起不来，登录必然失败。"
    if uses_local_postgres; then
      echo "（本机 PostgreSQL）"
      echo ""
      echo "请执行:"
      echo "  docker compose -f configs/compose/compose.yaml up -d postgres"
      echo "  docker compose -f configs/compose/compose.yaml logs postgres"
    else
      echo "（TCP 端口可能通，但 PostgreSQL 无响应，多为服务器 postgres 容器僵死）"
      echo ""
      echo "请在服务器 $(grep -E '^REMOTE_HOST=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo "172.19.134.45") 上执行："
      echo "  docker compose -p benxi restart postgres"
      echo "  # 或: EXPOSE_DEPS=1 bash scripts/stack.sh up postgres redis minio"
    fi
    echo ""
    echo "本机再试: ./dev.sh local restart"
    if [[ -f "$ENV_FILE" ]]; then
      grep -E '^DATABASE_URL=' "$ENV_FILE" | sed 's/:[^:@]*@/:***@/' || true
    fi
    return 1
  fi
  echo "  数据库连接正常"
}

api_health_ok() {
  curl -sf --max-time 8 "http://${HOST_BIND}:${API_PORT}/health" >/dev/null 2>&1
}

services_healthy() {
  api_health_ok \
    && curl -sf --max-time 3 "http://${HOST_BIND}:${WEB_PORT}/ai/" >/dev/null 2>&1
}

report_api_not_ready() {
  echo ""
  echo "API 未就绪 — 登录会失败（常见：远程 PostgreSQL 超时，/health 返回 503）。"
  echo "最近 API 日志："
  tail -15 "$LOG_DIR/platform-api.log" 2>/dev/null || true
  echo ""
  echo "若见 timeout expired / Application startup failed："
  echo "  服务器执行: docker compose -p benxi restart postgres"
  echo "  本机再试:   ./dev.sh local restart"
  echo "  实时日志:   ./dev.sh local logs"
}

ensure_skill_script_deps() {
  if "${PYTHON_CMD[@]}" -c 'import bs4, lxml' 2>/dev/null; then
    return 0
  fi
  step "安装 Skill 脚本沙箱依赖（beautifulsoup4、lxml）…"
  cd "$PLATFORM_DIR"
  if ! "${PYTHON_CMD[@]}" -m pip install "beautifulsoup4>=4.12.0" "lxml>=5.0.0" \
    >>"$LOG_DIR/local-dev.log" 2>&1; then
    echo "  Skill 沙箱依赖安装失败 — run_skill_script 可能报 No module named 'bs4'" >&2
    echo "  请手动执行: pip install 'beautifulsoup4>=4.12.0' 'lxml>=5.0.0'" >&2
    return 0
  fi
  echo "  Skill 沙箱依赖已就绪"
}

ensure_pageindex_extra() {
  if [[ "${SKIP_PAGEINDEX_INSTALL:-0}" == "1" ]]; then
    return 0
  fi
  if env PLATFORM="$PLATFORM_DIR" "${PYTHON_CMD[@]}" - <<'PY' 2>/dev/null; then
import os
import sys
from pathlib import Path

sys.path.insert(0, os.environ["PLATFORM"])
from app.integrations.pageindex_bridge import pageindex_package_available

raise SystemExit(0 if pageindex_package_available() else 1)
PY
    return 0
  fi
  step "安装 PageIndex 自托管依赖（pip install -e \".[pageindex]\"）…"
  cd "$PLATFORM_DIR"
  if ! "${PYTHON_CMD[@]}" -m pip install -e ".[pageindex]" >>"$LOG_DIR/local-dev.log" 2>&1; then
    echo "  PageIndex 安装失败 — 重新索引选 PageIndex 会提示「索引服务未就绪」" >&2
    echo "  请手动执行: cd platform && pip install -e '.[pageindex]'" >&2
    return 0
  fi
  "${PYTHON_CMD[@]}" -m pip install -e "./third_party/pageindex" >>"$LOG_DIR/local-dev.log" 2>&1 || true
  echo "  PageIndex 已就绪"
}

ensure_browser_rpa_deps() {
  if [[ "${SKIP_BROWSER_INSTALL:-0}" == "1" ]]; then
    return 0
  fi
  if "${PYTHON_CMD[@]}" -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
    return 0
  fi
  step "安装浏览器 RPA（Playwright + Chromium）…"
  cd "$PLATFORM_DIR"
  if ! "${PYTHON_CMD[@]}" -m pip install -e ".[browser]" >>"$LOG_DIR/local-dev.log" 2>&1; then
    echo "  浏览器 RPA 安装失败 — browser_navigate 会提示 Playwright 未安装" >&2
    echo "  请手动执行: ./dev.sh browser setup" >&2
    return 0
  fi
  if ! "${PYTHON_CMD[@]}" -m playwright install chromium >>"$LOG_DIR/local-dev.log" 2>&1; then
    echo "  Chromium 下载失败 — 请手动执行: ./dev.sh browser setup" >&2
    return 0
  fi
  echo "  浏览器 RPA 已就绪"
}

start_local() {
  local force="${1:-0}"
  init_paths

  if [[ "$force" != "1" ]] && services_healthy; then
    echo "服务已在运行（API :${API_PORT} + 前端 :${WEB_PORT} 正常），无需重启。"
    echo "  访问: http://127.0.0.1:${WEB_PORT}/ai/"
    echo "  状态: ./dev.sh local status"
    echo "  强制重启: ./dev.sh local restart"
    return 0
  fi

  rotate_logs

  local app_name version
  app_name="$(read_platform_app_name "$ROOT")"
  version="$(read_repo_version "$ROOT")"
  echo "正在启动 ${app_name} v${version}（本机 API + 前端）…"

  ensure_conda_env || return 1
  ensure_skill_script_deps
  ensure_pageindex_extra
  ensure_browser_rpa_deps
  preflight_database || return 1

  step "停止已有进程（API / 前端 / Worker）…"
  stop_local
  sleep 1

  cd "$PLATFORM_DIR"
  local api_pid worker_pid web_pid

  local -a uvicorn_args=("${UVICORN_CMD[@]}" app.main:app --host "$HOST_BIND" --port "$API_PORT")
  if is_remote_deps && [[ "${LOCAL_DEV_RELOAD:-0}" != "1" ]]; then
    step "启动 API（uvicorn :${API_PORT}，remote-dev 无热重载）…"
  else
    step "启动 API（uvicorn :${API_PORT}）…"
    uvicorn_args+=(--reload)
  fi
  api_pid="$(start_detached "$LOG_DIR/platform-api.log" "${uvicorn_args[@]}")"
  echo "$api_pid" >"$RUN_DIR/platform-api.pid"
  echo "  pid=$api_pid  日志: $LOG_DIR/platform-api.log"

  worker_pid=""
  step "检测远程 Celery Worker（连接 Redis，约 3–10 秒）…"
  if should_start_worker; then
    step "启动本地 Celery Worker…"
    worker_pid="$(start_detached "$LOG_DIR/platform-worker.log" \
      "${CELERY_CMD[@]}" -A workers.celery_app worker --loglevel=info --concurrency=4)"
    echo "$worker_pid" >"$RUN_DIR/platform-worker.pid"
    echo "  pid=$worker_pid  日志: $LOG_DIR/platform-worker.log"
  else
    rm -f "$RUN_DIR/platform-worker.pid"
    step "跳过本地 Worker（远程已有 Worker；强制本地: START_LOCAL_WORKER=1）"
    echo "$(date '+%F %T') 检测到远程 Celery Worker，跳过本地 Worker（强制本地：START_LOCAL_WORKER=1）" \
      >>"$LOG_DIR/local-dev.log"
  fi

  cd "$ROOT/frontend"
  step "启动前端（Vite :${WEB_PORT}）…"
  web_pid="$(start_detached "$LOG_DIR/platform-frontend.log" \
    ./node_modules/.bin/vite --host "$HOST_BIND" --port "$WEB_PORT")"
  echo "$web_pid" >"$RUN_DIR/platform-frontend.pid"
  echo "  pid=$web_pid  日志: $LOG_DIR/platform-frontend.log"

  local wait_secs=30
  if [[ -f "$ENV_FILE" ]] && grep -q '^REMOTE_DEPS=1' "$ENV_FILE" 2>/dev/null && ! uses_local_postgres; then
    wait_secs=30
  fi
  if uses_local_postgres; then
    step "等待 API 与前端就绪（最多 ${wait_secs} 秒）…"
  else
    step "等待 API 与前端就绪（最多 ${wait_secs} 秒，远程库首次可能较慢）…"
  fi
  local i api_ok=0 web_ok=0
  for i in $(seq 1 "$wait_secs"); do
    curl -sf --max-time 2 "http://${HOST_BIND}:${API_PORT}/health" >/dev/null 2>&1 && api_ok=1
    curl -sf --max-time 2 "http://${HOST_BIND}:${WEB_PORT}/ai/" >/dev/null 2>&1 && web_ok=1
    if [[ "$api_ok" -eq 1 && "$web_ok" -eq 1 ]]; then
      echo "  就绪（${i}s）— API ✓  前端 ✓"
      break
    fi
    local api_st web_st
    api_st=$([[ "$api_ok" -eq 1 ]] && echo "✓" || echo "…")
    web_st=$([[ "$web_ok" -eq 1 ]] && echo "✓" || echo "…")
    printf "  [%2d/%s] API %s  前端 %s\r" "$i" "$wait_secs" "$api_st" "$web_st"
    sleep 1
  done
  echo ""
  if [[ "$api_ok" -ne 1 || "$web_ok" -ne 1 ]]; then
    echo "  超时 — API ${api_st:-…}  前端 ${web_st:-…}（见上方日志文件）"
  fi

  # 远程 PG 场景：API 启动失败时提示用户检查 PG 端口映射
  if [[ "$api_ok" -ne 1 ]] && ! uses_local_postgres && is_remote_deps; then
    local remote_host
    remote_host="$(grep -E '^REMOTE_HOST=' "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\r' || true)"
    remote_host="${remote_host:-172.19.134.45}"
    if grep -q 'OperationalError\|Connection refused\|could not connect to server' "$LOG_DIR/platform-api.log" 2>/dev/null; then
      echo "  → API 日志显示数据库连接失败，请检查服务器 ${remote_host} 的 Postgres 端口映射（40002）"
      echo "    手动修复: ssh root@${remote_host} 'cd /root/qzb/benxi && docker compose -f configs/compose/compose.yaml -f configs/compose/compose.server.yaml -f configs/compose/compose.expose-deps.yaml up -d postgres --force-recreate'"
    fi
  fi

  if command -v lsof >/dev/null 2>&1; then
    lsof -ti :"${API_PORT}" >/dev/null 2>&1 || {
      echo "API 端口 ${API_PORT} 未监听，请查看 $LOG_DIR/platform-api.log"
      tail -20 "$LOG_DIR/platform-api.log" || true
      return 1
    }
    lsof -ti :"${WEB_PORT}" >/dev/null 2>&1 || {
      echo "前端端口 ${WEB_PORT} 未监听，请查看 $LOG_DIR/platform-frontend.log"
      tail -20 "$LOG_DIR/platform-frontend.log" || true
      return 1
    }
  fi

  {
    echo "API pid=$api_pid (http://${HOST_BIND}:${API_PORT})"
    if [[ -n "$worker_pid" ]]; then
      echo "Worker pid=$worker_pid (本地 Celery → 远程 Redis)"
    else
      echo "Worker: 使用远程服务器上的 Celery Worker"
    fi
    echo "WEB pid=$web_pid"
  } | tee -a "$LOG_DIR/local-dev.log"

  step "校验 API 版本与前端响应…"
  curl -sf --max-time 10 "http://${HOST_BIND}:${API_PORT}/api/v1/system/version" || {
    echo "API not ready"
    report_api_not_ready
    return 1
  }
  echo
  curl -sf -o /dev/null -w "frontend HTTP %{http_code}\n" \
    "http://${HOST_BIND}:${WEB_PORT}/ai/"
  echo
  echo "${app_name} 已就绪，请用浏览器打开："
  echo "  http://localhost:${WEB_PORT}/ai/"
  echo "  http://${HOST_BIND}:${WEB_PORT}/ai/"
  echo
  echo "服务已在后台运行（脚本会退出，进程不会停）。"
  echo "  状态: ./dev.sh local status"
  echo "  日志: ./dev.sh local logs"
  echo "  停止: ./dev.sh stop"
}

logs_local() {
  init_paths
  local files=()
  [[ -f "$LOG_DIR/platform-api.log" ]] && files+=("$LOG_DIR/platform-api.log")
  [[ -f "$LOG_DIR/platform-frontend.log" ]] && files+=("$LOG_DIR/platform-frontend.log")
  [[ -f "$LOG_DIR/platform-worker.log" ]] && files+=("$LOG_DIR/platform-worker.log")
  if [[ ${#files[@]} -eq 0 ]]; then
    echo "尚无日志，请先 ./dev.sh local" >&2
    exit 1
  fi
  echo "跟踪日志（Ctrl+C 仅退出本命令，不停止服务）…"
  tail -n 30 -F "${files[@]}"
}

status_local() {
  init_paths

  check_port() {
    local port=$1 label=$2
    if lsof -ti :"$port" >/dev/null 2>&1; then
      echo "OK  $label  :$port"
    else
      echo "DOWN $label :$port"
    fi
  }

  check_port "$API_PORT" "API"
  check_port "$WEB_PORT" "WEB"

  local health_code
  health_code="$(curl -sf --max-time 8 -o /dev/null -w '%{http_code}' \
    "http://${HOST_BIND}:${API_PORT}/health" 2>/dev/null || echo "000")"
  if [[ "$health_code" == "200" ]]; then
    echo "OK  API /health（含数据库）"
  elif [[ "$health_code" == "503" ]]; then
    echo "FAIL API /health — 数据库不可用（remote-dev 请检查 172.19.134.45:40002）"
  else
    echo "FAIL API /health（HTTP ${health_code}）"
  fi

  if curl -sf --max-time 3 "http://${HOST_BIND}:${WEB_PORT}/ai/" >/dev/null 2>&1; then
    echo "OK  frontend /ai/"
  else
    echo "FAIL frontend /ai/"
  fi

  run_with_timeout 10 env ENV_FILE="$ENV_FILE" PLATFORM="$PLATFORM_DIR" \
    "${PYTHON_CMD[@]}" - <<'PY' 2>/dev/null || echo "celery workers (broker): unknown (timeout)"
import os
import sys
from pathlib import Path

platform = Path(os.environ["PLATFORM"])
sys.path.insert(0, str(platform))
env = {}
for line in Path(os.environ["ENV_FILE"]).read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    env[k.strip()] = v.strip()
url = env.get("REDIS_URL") or env.get("CELERY_BROKER_URL") or ""
if not url:
    print("celery workers (broker): 0 (no REDIS_URL)")
    raise SystemExit
try:
    from workers.celery_app import celery_app

    celery_app.conf.broker_url = url
    ping = celery_app.control.inspect(timeout=3).ping() or {}
    names = ", ".join(sorted(ping.keys())) or "(none)"
    print(f"celery workers (broker): {len(ping)} [{names}]")
except Exception as exc:
    print(f"celery workers (broker): unknown ({exc})")
PY

  if pgrep -fl "celery -A workers.celery_app worker" >/dev/null 2>&1; then
    echo "OK  local celery worker"
  else
    echo "—   local celery worker (not running; remote may cover tasks)"
  fi
}

cmd="${1:-start}"

case "$cmd" in
  start|up|"")
    start_local 0
    ;;
  status|st)
    status_local
    ;;
  stop|down)
    stop_local
    echo "已停止本机 API / 前端 / Worker"
    ;;
  restart)
    stop_local
    sleep 1
    start_local 1
    ;;
  logs|log|follow)
    logs_local
    ;;
  -h|--help|help)
    sed -n '2,9p' "$0" | sed 's/^# \?//'
    ;;
  *)
    echo "未知命令: $cmd" >&2
    echo "用法: ./dev.sh local [start|status|stop|restart|logs]" >&2
    exit 1
    ;;
esac
