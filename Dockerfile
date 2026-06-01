ARG BASE_IMAGE=ghcr.io/astral-sh/uv:python3.13-bookworm-slim
FROM ${BASE_IMAGE}

# 镜像站部署若无法拉 ghcr，可传 BASE_IMAGE=docker.1ms.run/library/python:3.11-slim 并在下方安装 uv
RUN if ! command -v uv >/dev/null 2>&1; then pip install --no-cache-dir uv; fi

WORKDIR /app

EXPOSE 7860

ENV PYTHONUNBUFFERED=1

RUN apt-get update && \
     apt-get install --no-install-recommends -y libgl1 libglib2.0-0 libxext6 libsm6 libxrender1 build-essential && \
     rm -rf /var/lib/apt/lists/*

# 离线资源：Mac/服务器预先放入 assets/babeldoc 或 assets/offline_assets_*.zip
COPY assets/ /assets/

COPY pyproject.toml .
RUN uv pip install --system --no-cache -r pyproject.toml && \
    if [ -d /assets/babeldoc/models ] && [ -n "$(ls -A /assets/babeldoc/models 2>/dev/null)" ]; then \
      mkdir -p /root/.cache && rm -rf /root/.cache/babeldoc && cp -a /assets/babeldoc /root/.cache/babeldoc; \
    elif ls /assets/offline_assets_*.zip >/dev/null 2>&1; then \
      python -c "from pathlib import Path; from babeldoc.assets.assets import restore_offline_assets_package; restore_offline_assets_package(Path('/assets'))"; \
    else \
      echo "WARN: no offline babeldoc assets under /assets; build may need network for warmup" >&2; \
      babeldoc --warmup; \
    fi && \
    babeldoc --version

COPY . .

# Calls for a random number to break the caching of babeldoc upgrade
# (https://stackoverflow.com/questions/35134713/disable-cache-for-specific-run-commands/58801213#58801213)
ADD "https://www.random.org/cgi-bin/randbyte?nbytes=10&format=h" skipcache

RUN uv pip install --system --no-cache . && uv pip install --system --no-cache --compile-bytecode -U babeldoc "pymupdf<1.25.3" && \
    if [ ! -d /root/.cache/babeldoc/models ] || [ -z "$(ls -A /root/.cache/babeldoc/models 2>/dev/null)" ]; then \
      if [ -d /assets/babeldoc/models ] && [ -n "$(ls -A /assets/babeldoc/models 2>/dev/null)" ]; then \
        mkdir -p /root/.cache && rm -rf /root/.cache/babeldoc && cp -a /assets/babeldoc /root/.cache/babeldoc; \
      elif ls /assets/offline_assets_*.zip >/dev/null 2>&1; then \
        python -c "from pathlib import Path; from babeldoc.assets.assets import restore_offline_assets_package; restore_offline_assets_package(Path('/assets'))"; \
      else \
        babeldoc --warmup; \
      fi; \
    fi && \
    babeldoc --version
RUN pdf2zh --version
CMD ["pdf2zh", "--gui"]
