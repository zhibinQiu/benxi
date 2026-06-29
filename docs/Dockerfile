# MkDocs Material 文档站（profile docs）
ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}

WORKDIR /site

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
COPY docs/requirements-docs.txt /tmp/requirements-docs.txt
RUN pip install --no-cache-dir -r /tmp/requirements-docs.txt -i "${PIP_INDEX_URL}"

COPY mkdocs.yml .
COPY docs/zh docs/zh
COPY icon icon

EXPOSE 8000
CMD ["mkdocs", "serve", "-a", "0.0.0.0:8000"]
