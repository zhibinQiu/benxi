# Docker 容器说明

统一栈项目名 **`zhitan`**，网络 **`zhitan`**（bridge）。除 `frontend` 外，**默认不映射主机端口**。

> 各数据库存储内容与连接方式见 **[组件位置与数据存储](components-and-storage.md)**。

## 核心服务（始终启动）

| 容器名 | Compose 服务 | 镜像 | 容器端口 | 职责 |
|--------|--------------|------|----------|------|
| `zhitan-postgres-1` | postgres | postgres:16-alpine | 5432 | 平台业务库：用户、RBAC、文档元数据、任务、审计 |
| `zhitan-redis-1` | redis | redis:7-alpine | 6379 | Celery broker、缓存、KnowFlow 可选 Redis |
| `zhitan-minio-1` | minio | minio/minio | 9000/9001 | 文档对象存储；KnowFlow 共用 |
| `zhitan-pdf2zh-api-1` | pdf2zh-api | zhitan-pdf2zh:${ZHITAN_VERSION} | 7861 | PDF 翻译 REST；BabelDOC 模型预热 |
| `zhitan-api-1` | api | zhitan-api:${ZHITAN_VERSION} | 8000 | FastAPI：鉴权、文档、插件 API、embed-proxy |
| `zhitan-worker-1` | worker | 同 api | — | Celery：翻译、对比、同步 KnowFlow 等长任务 |
| `zhitan-frontend-1` | frontend | zhitan-frontend 或 dev 时 node:22 | 80 | **唯一对外** `${FRONTEND_PORT:-40005}`；Nginx 或 Vite |

### 健康检查

- postgres / redis / minio / pdf2zh-api：compose 内 healthcheck
- api：依赖上游 healthy 后启动
- pdf2zh 首次启动可能 **3 分钟+**（模型 warmup）

## Profile：`speech`

| 容器 | 镜像 | 端口 | 职责 |
|------|------|------|------|
| `zhitan-speech-api-1` | zhitan-speech | 8765 | FunASR 转写；模型卷 `${DATA_ROOT}/speech-models` |

开发栈 `compose.dev.yaml` 可将 `SPEECH_SERVICE_URL` 指向 `host.docker.internal:8765`（宿主机 FunASR）。

## Profile：`knowflow`（`deploy/knowflow.yml`）

| 容器 | 镜像 | 端口 | 职责 |
|------|------|------|------|
| `ragflow-mysql` | mysql:8.0.39 | 3306 | RAGFlow / KnowFlow 元数据 |
| `ragflow-infinity` | infiniflow/infinity | 23820 | Infinity 向量与全文索引 |
| `knowflow-gotenberg` | gotenberg/gotenberg:8 | 3000 | 文档格式转换 |
| `ragflow-server` | knowflow-ragflow:source 或预构建 | **80**（内 nginx） | RAGFlow Web UI + API（内网 9380） |
| `knowflow-backend` | knowflow-server:source | 5000 | KnowFlow 管理 API、RBAC 扩展 |

**依赖顺序：** mysql / infinity healthy → ragflow → knowflow-backend。

**数据卷：** `${DATA_ROOT}/knowflow-mysql`、`knowflow-infinity`、`knowflow-logs`。

**配置挂载：**

- `deploy/knowflow/nginx/*` → ragflow 容器 nginx
- `deploy/knowflow/infinity_conf.toml` → infinity 容器
- `deploy/knowflow/theme/*` → RAGFlow 静态白标
- `deploy/knowflow/settings.yaml` → knowflow-backend

## 开发模式差异（`compose.dev.yaml`）

| 服务 | 变化 |
|------|------|
| api | `127.0.0.1:18000→8000`；挂载 `platform/app`；`uvicorn --reload` |
| frontend | Node + Vite；`VITE_API_BASE=http://127.0.0.1:18000` |
| worker | 挂载源码 |

## 常用命令

```bash
docker compose -p zhitan ps
docker compose -p zhitan logs -f api
docker compose -p zhitan logs -f ragflow-server   # 需 knowflow profile
bash scripts/stack.sh backup    # postgres + minio 快照
```
