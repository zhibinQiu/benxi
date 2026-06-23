# syntax=docker/dockerfile:1
# 平台 API Python 运行时镜像（构建上下文 = 仓库根目录）
#
# 目标:
#   runtime    — 仅 Python 依赖，运行时挂载 platform/app、workers（服务器快速部署 / 热更新）
#   production — 依赖 + 业务代码 baked-in（离线 save/load、无挂载生产）
#
# 构建:
#   docker build -f platform/Dockerfile --target runtime -t zhitan-api-runtime:4.0.4 .
#   docker buildx build --platform linux/amd64,linux/arm64 --target runtime --push \
#     -t registry.cn-hangzhou.aliyuncs.com/<ns>/zhitan-api-runtime:4.0.4 .

ARG PYTHON_IMAGE=python:3.11-slim
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG APT_MIRROR=mirrors.tuna.tsinghua.edu.cn
ARG INSTALL_PAGEINDEX=0
ARG INSTALL_BROWSER=0

FROM ${PYTHON_IMAGE} AS base
ARG PIP_INDEX_URL
ARG APT_MIRROR
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app
WORKDIR /app

RUN if [ -n "${APT_MIRROR}" ] && [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i "s|deb.debian.org|${APT_MIRROR}|g; s|security.debian.org|${APT_MIRROR}|g" \
        /etc/apt/sources.list.d/debian.sources; \
    elif [ -n "${APT_MIRROR}" ] && [ -f /etc/apt/sources.list ]; then \
      sed -i "s|deb.debian.org|${APT_MIRROR}|g; s|security.debian.org|${APT_MIRROR}|g" \
        /etc/apt/sources.list; \
    fi && \
    apt-get update && apt-get install -y --no-install-recommends \
    fonts-wqy-microhei \
    && rm -rf /var/lib/apt/lists/*

# --- 安装 Python 依赖（不复制业务代码）---
FROM base AS deps
ARG PIP_INDEX_URL
ARG INSTALL_PAGEINDEX
ARG INSTALL_BROWSER

COPY platform/pyproject.toml platform/README.md ./

# hatchling 打 wheel 需要包目录；runtime 由 volume 挂载真实 app/workers
RUN mkdir -p app workers && touch app/__init__.py workers/__init__.py

# PageIndex 可选；仅 INSTALL_PAGEINDEX=1 时安装 extra
COPY platform/third_party/pageindex-upstream ./third_party/pageindex-upstream/

RUN pip install --no-cache-dir --upgrade "pip>=24.0" && \
    pip install --no-cache-dir -i "${PIP_INDEX_URL}" . && \
    if [ "${INSTALL_PAGEINDEX}" = "1" ]; then \
      pip install --no-cache-dir -i "${PIP_INDEX_URL}" ".[pageindex]" && \
      cfg_dir="$(python -c 'import pageindex, pathlib; print(pathlib.Path(pageindex.__file__).parent)')" && \
      cp third_party/pageindex-upstream/pageindex/config.yaml "${cfg_dir}/config.yaml"; \
    fi && \
    if [ "${INSTALL_BROWSER}" = "1" ]; then \
      pip install --no-cache-dir -i "${PIP_INDEX_URL}" ".[browser]" && \
      python -m playwright install-deps chromium && \
      python -m playwright install chromium; \
    fi && \
    find /usr/local/lib/python3.11 -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

RUN python -c "\
import fastapi, sqlalchemy, celery, httpx, pandas, numpy, bs4, lxml; \
print('core deps ok', fastapi.__version__)\
"

# --- runtime：服务器挂载源码 ---
FROM deps AS runtime
COPY RELEASE.md ./
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# --- production：离线交付 / stack save ---
FROM deps AS production
COPY RELEASE.md ./
COPY platform/app ./app
COPY platform/workers ./workers
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
