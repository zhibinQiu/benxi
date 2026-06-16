ARG PYTHON_IMAGE=python:3.11-slim
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
FROM ${PYTHON_IMAGE}
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

WORKDIR /app

# 系统说明文档（构建上下文为仓库根目录）
COPY docs ./system-docs/docs
COPY 运维部署指南.md ./system-docs/
COPY RELEASE.md ./system-docs/
ENV SYSTEM_DOCS_ROOT=/app/system-docs

# 数据分析 Notebook 绘图需中文字体（matplotlib 默认 DejaVu Sans 不含 CJK）
RUN apt-get update && apt-get install -y --no-install-recommends fonts-wqy-microhei \
    && rm -rf /var/lib/apt/lists/*

COPY platform/pyproject.toml platform/README.md ./
COPY platform/app ./app
COPY platform/workers ./workers

RUN pip install --no-cache-dir -i "${PIP_INDEX_URL}" -e . && \
    python -c "\
import pandas, openpyxl, numpy, matplotlib, seaborn; \
print('data-analysis deps:', pandas.__version__, openpyxl.__version__)\
"

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
