# MkDocs Material 文档站（profile docs）
# mkdocs.yml 中 docs_dir: ../docs/zh（相对项目根 configs/），
# 故本 Dockerfile 将 docs 置于 /site/ 上一层。
ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
COPY docs/requirements-docs.txt /tmp/requirements-docs.txt
RUN pip install --no-cache-dir -r /tmp/requirements-docs.txt -i "${PIP_INDEX_URL}"

# mkdocs.yml at /site/mkdocs.yml → ../docs/zh = /docs/zh
WORKDIR /site
COPY configs/mkdocs.yml .
COPY docs/zh /docs/zh
COPY icon /icon

EXPOSE 8000
CMD ["mkdocs", "serve", "-a", "0.0.0.0:8000"]
