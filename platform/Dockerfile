ARG PYTHON_IMAGE=python:3.11-slim
FROM ${PYTHON_IMAGE}

WORKDIR /app

# psycopg2-binary 无需 libpq-dev；避免构建时 apt 网络失败
COPY pyproject.toml README.md ./
COPY app ./app
COPY workers ./workers

RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
