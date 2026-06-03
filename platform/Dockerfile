ARG PYTHON_IMAGE=python:3.11-slim
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
FROM ${PYTHON_IMAGE}
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

WORKDIR /app

# 数据分析 Notebook 绘图需中文字体（matplotlib 默认 DejaVu Sans 不含 CJK）
RUN apt-get update && apt-get install -y --no-install-recommends fonts-wqy-microhei \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app
COPY workers ./workers
# KnowFlow iframe 白标资源（与 deploy/knowflow/theme 保持一致）
COPY knowflow-theme ./knowflow-theme

RUN pip install --no-cache-dir -i "${PIP_INDEX_URL}" -e . && \
    python -c "\
import pandas, openpyxl, numpy, matplotlib, seaborn; \
print('data-analysis deps:', pandas.__version__, openpyxl.__version__)\
"

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
