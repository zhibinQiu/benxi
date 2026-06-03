# 智碳平台后端（FastAPI + Celery）

## 运行方式（v3.4+）

**请使用仓库根目录统一 Docker 栈**，勿再使用本目录下已删除的 `docker-compose*.yml`。

```bash
cd ..   # 仓库根 pdf_trans
bash scripts/stack.sh dev-up --profile knowflow
```

- API 开发：http://127.0.0.1:18000
- 配置：根目录 `.env` + `platform/.env.example` 中的业务项

## 目录

```
platform/
├── app/           # FastAPI 应用、功能插件、域服务
├── workers/       # Celery worker
├── tests/         # pytest
├── knowflow-theme/  # embed-proxy 白标（与 deploy/knowflow/theme 同步）
├── speech-service/  # FunASR 镜像构建上下文
└── Dockerfile
```

## 文档

- [运维手册](../docs/zh/operations/README.md)
- [后端实现](../docs/zh/implementation/backend-implementation.md)
- [API 约定](../docs/zh/implementation/api-conventions.md)

## 本地 pytest（可选）

```bash
cd platform && pip install -e ".[dev]" && pytest tests/ -q
```
