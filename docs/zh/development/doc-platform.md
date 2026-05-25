# 智碳 AI平台

智碳 AI 企业应用平台：**用户 / 部门 / 角色 / 文档 ACL / 异步任务 / 站内通知 / 审计**。  
PDF 翻译经平台任务队列调用 `pdf2zh_next --api`（默认 `http://127.0.0.1:7861`）。

## 模块

| 目录 | 说明 |
|------|------|
| `platform/` | FastAPI 后端、Celery Worker |
| `platform-frontend/` | Vue 3 管理界面（:5174） |
| `pdf2zh_next/` | 翻译引擎（:7861） |

## 一键启动

```bash
# 仓库根目录
bash scripts/start_platform.sh        # 本地优先（默认）
bash scripts/start_platform.sh docker # 宿主机 pdf2zh + Docker 平台
bash scripts/stop_platform.sh
```

| 服务 | 地址 |
|------|------|
| 平台前端 | http://127.0.0.1:5174 |
| 平台 API | http://127.0.0.1:8000 |
| pdf2zh API | http://127.0.0.1:7861 |
| MinIO 控制台 | http://127.0.0.1:9001 |

默认管理员：`admin` / `admin123`（`platform/.env` 中 `BOOTSTRAP_ADMIN_*`）。

## 本地开发（不用 Docker 跑应用）

```bash
# 基础设施仍可用 Docker
cd platform && docker compose -f docker-compose.yml -f docker-compose.local.yml up -d postgres redis minio

cd platform && source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# 另开终端
celery -A workers.celery_app worker --loglevel=info

cd platform-frontend && npm run dev
```

根目录 `.venv` 中启动翻译 API：

```bash
pdf2zh_next --api --api-port 7861
```

## API 前缀

`/api/v1` — 登录、文档、任务、翻译代理、通知、审计等。Swagger：`http://127.0.0.1:8000/docs`。

## 知识问答（KnowFlow）

Apple Silicon 推荐 **从源码构建**（官方 `zxwei/knowflow` 镜像仅 amd64）：

```bash
bash scripts/setup_knowflow.sh          # 克隆 KnowFlow 到 platform/third_party/KnowFlow
bash scripts/build_knowflow_source.sh   # 构建 deps + RAGFlow + KnowFlow Server（首次 30–90 分钟）
bash scripts/start_platform.sh knowflow # 启动基础设施 + 应用
```

在 `platform/.env` 中可选：`KNOWFLOW_ENABLED=true`、`RAGFLOW_API_KEY=...`（RAGFlow 控制台获取）。

前端：**系统功能 → 知识问答**（iframe 嵌入 `http://127.0.0.1:9380`，保留溯源与 PDF 定位等完整能力）。

| 服务 | 地址 |
|------|------|
| RAGFlow UI | http://127.0.0.1:9380 |
| KnowFlow API | http://127.0.0.1:5001 |

编排：单一文件 `platform/docker-compose.knowflow.yml`（基础组件 + 源码构建服务；原预构建镜像配置已注释）。

## 功能插件

见 [platform/feature-plugins.md](../platform/feature-plugins.md)。

## 文档上传流程

1. `POST /api/v1/documents`
2. `POST /api/v1/documents/{id}/upload/prepare`
3. 客户端 `PUT` 至 MinIO 预签名 URL
4. `POST /api/v1/documents/{id}/upload/complete`
5. `GET /api/v1/documents/{id}/download`
