# 组件位置与数据存储（v3.9.3）

> **本文描述当前系统的真实部署形态**：各服务跑在哪里、数据存在哪、如何连接查看。  
> 启动与部署命令见 [运维部署指南](../../../运维部署指南.md)；容器细节见 [Docker 容器说明](docker-services.md)。

---

## 1. 当前系统是什么

绿叶 AI 办公系统 使用 **单一 Docker Compose 栈**（项目名 `zhitan`），所有服务在同一 Docker 网络 `zhitan` 内通信。

| 项 | 当前做法 |
|----|----------|
| 编排入口 | `bash scripts/stack.sh`（build / up / dev-up / backup） |
| 日常开发 | `./dev.sh docker`（全 Docker 热重载） |
| 对外 Web | 仅 **40005**（Nginx 或 Vite） |
| 知识库向量引擎 | **Infinity**（`DOC_ENGINE=infinity`），**不是** Elasticsearch |
| 对象存储 | 栈内 **MinIO**，平台与 KnowFlow **共用** |
| 平台业务库 | **PostgreSQL 16** |
| KnowFlow 元数据库 | **MySQL 8**（库名 `rag_flow`） |

### 已废弃（请勿在新环境使用）

| 废弃方式 | 替代 |
|----------|------|
| `platform/docker-compose*.yml` 多文件组合 | 根目录 `compose.yaml` + `deploy/knowflow.yml` |
| `bash scripts/merge-stack-env.sh` | `bash scripts/setup-stack-env.sh` |
| `./dev.sh legacy` | `./dev.sh docker` |
| `bash scripts/deploy.sh full`（rsync 全仓库远程 build） | `stack build` + `stack save` + `deploy.sh stack push` |
| 独立 Elasticsearch 向量库 | Infinity（`knowflow-infinity` 容器） |

远程依赖开发（`remote-dev` + `./dev.sh local`）仅为**过渡方案**，目标形态是单机 `dev.sh docker`；见 [单机迁移与热重载](single-server-migration.md)。

---

## 2. 组件位置一览

### 2.1 服务与容器

| Compose 服务 | 容器名（典型） | 镜像 | 容器端口 | 宿主机端口 | 职责 |
|--------------|----------------|------|----------|------------|------|
| `frontend` | `zhitan-frontend-1` | zhitan-frontend | 80 | **40005** | 唯一 Web 入口；反代 SPA、API、KnowFlow iframe |
| `api` | `zhitan-api-1` | zhitan-api | 8000 | 开发时 **18000** | FastAPI：鉴权、文档、插件、embed-proxy |
| `worker` | `zhitan-worker-1` | zhitan-api | — | 不映射 | Celery 异步任务 |
| `postgres` | `zhitan-postgres-1` | postgres:16-alpine | 5432 | 不映射 | 平台业务库 |
| `redis` | `zhitan-redis-1` | redis:7-alpine | 6379 | 不映射 | Celery 队列、缓存 |
| `minio` | `zhitan-minio-1` | minio/minio | 9000/9001 | 不映射 | S3 对象存储 |
| `pdf2zh-api` | `zhitan-pdf2zh-api-1` | zhitan-pdf2zh | 7861 | 不映射 | PDF 翻译 REST |
| `speech-api` | `zhitan-speech-api-1` | zhitan-speech | 8765 | 不映射 | 语音转写（profile `speech`） |
| `knowflow-mysql` | `ragflow-mysql` | mysql:8.0.39 | 3306 | 不映射 | KnowFlow 元数据 |
| `knowflow-infinity` | `ragflow-infinity` | infiniflow/infinity | 23820 | 不映射 | 向量与全文索引 |
| `ragflow` | `ragflow-server` | knowflow-ragflow | 80 / 9380 | 不映射 | RAGFlow Web + API |
| `knowflow-backend` | `knowflow-backend` | knowflow-server | 5000 | 不映射 | KnowFlow 管理 API |
| `knowflow-gotenberg` | `knowflow-gotenberg` | gotenberg:8 | 3000 | 不映射 | Office → PDF |

容器间访问 **必须用 Docker 服务名**（如 `postgres`、`minio`、`ragflow`），不能写 `127.0.0.1`（浏览器地址除外）。

### 2.2 宿主机数据目录（`DATA_ROOT`，默认 `./data`）

```
data/
├── postgres/           # PostgreSQL 数据文件
├── minio/              # MinIO 对象（含 documents 桶与 KnowFlow 对象）
├── pdf2zh-config/      # BabelDOC 模型与配置缓存
├── speech-models/      # FunASR 模型（profile speech）
├── knowflow-mysql/     # KnowFlow MySQL 数据文件
├── knowflow-infinity/  # Infinity 向量/全文索引文件
└── knowflow-logs/      # RAGFlow 运行日志
```

备份目录：`backups/<时间戳>/`（`stack.sh backup` 生成 `postgres.sql.gz`、`knowflow-mysql.sql.gz`、`minio.tar.gz`）。

### 2.3 代码与配置位置

| 路径 | 内容 |
|------|------|
| `compose.yaml` | 核心服务定义 |
| `compose.dev.yaml` | 开发覆盖（API :18000、Vite 热重载） |
| `deploy/knowflow.yml` | KnowFlow profile 服务 |
| `deploy/knowflow/settings.yaml` | knowflow-backend 业务配置 |
| `platform/app/` | FastAPI 后端源码 |
| `platform-frontend/` | Vue 3 前端 |
| `pdf2zh_next/` | PDF 翻译引擎 |
| `.env` | 栈运行时配置（不提交 Git） |
| `platform/.env` | 业务密钥模板源（JWT、API Key 等） |

---

## 3. 各存储介质存什么

### 3.1 PostgreSQL（平台业务库）

- **容器**：`postgres`（别名无，DNS 名即 `postgres`）
- **连接串**（容器内）：`postgresql+psycopg2://platform:platform@postgres:5432/platform`
- **账号**：`.env` 中 `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`（默认均为 `platform`）
- **迁移**：启动时 `create_all` + `schema_migrate.py` 自动补丁（非 Alembic）

| 域 | 主要表 | 存储内容 |
|----|--------|----------|
| 用户与组织 | `users`、`departments`、`user_departments`、`roles`、`permissions`、`role_permissions`、`user_roles` | 账号、部门树、RBAC |
| 文档元数据 | `documents`、`document_library_folders`、`document_versions`、`document_permissions`、`document_version_blocks` | 文档记录、文件夹、版本、ACL、对比块 |
| 文档流程 | `document_access_denials`、`document_publish_requests` | 拒绝访问、发布申请 |
| KnowFlow 映射（平台侧） | `ragflow_account_links`、`ragflow_scope_datasets`、`ragflow_document_links`、`ragflow_document_version_links`、`ragflow_document_mirror_links` | 平台用户 ↔ RAGFlow 账号、scope dataset、文档同步状态；**存在即复用、孤儿清理**见 [知识库数据一致性](knowledge-data-consistency.md) |
| 后台任务 | `jobs`、`job_events` | 翻译、对比、同步等任务及事件流 |
| 文档对比 | `compare_jobs`、`compare_diff_items`、`compare_search_hits`、`document_version_compare_relations`、`document_version_diff_items` | 对比任务与 diff 结果 |
| 对话 | `rag_sessions`、`rag_messages`、`platform_chat_conversations`、`platform_chat_messages` | RAG 问答与平台助手会话 |
| 订阅资讯 | `feed_sources`、`feed_entries`、`wechat_mp_*` 等 | RSS / 公众号源与条目 |
| 其他 | `todo_items`、`meeting_records`、`notifications`、`audit_logs`、`cea_daily_quotes`、`ccer_daily_quotes`、`platform_model_settings` | 待办、会议、通知、审计、碳行情、在线模型配置 |

**平台不存**：PDF/Office 原文件二进制（在 MinIO）、向量嵌入（在 Infinity）、RAGFlow 切片明细（在 MySQL + Infinity）。

### 3.2 MySQL（KnowFlow / RAGFlow 元数据）

- **容器**：`knowflow-mysql`（DNS 别名 `mysql`）
- **库名**：`rag_flow`（`deploy/knowflow/init.sql` 初始化）
- **账号**：`root` / 密码为 `.env` 中 `MYSQL_PASSWORD`（默认 `infini_rag_flow`）

存储 RAGFlow 原厂 schema：用户与租户、知识库（dataset）、文档记录、解析任务、切片元数据、对话会话、模型配置等。**向量数值本身不在 MySQL**，在 Infinity。

### 3.3 Infinity（向量与全文索引）

- **容器**：`knowflow-infinity`（DNS 别名 `infinity`）
- **数据目录**：`${DATA_ROOT}/knowflow-infinity`
- **HTTP 管理端口**：容器内 `23820`
- **配置**：`deploy/knowflow/infinity_conf.toml`

存储 embedding 向量与全文检索索引的二进制文件，**不能**用常规 SQL 客户端查看；通过 RAGFlow API 或 Infinity HTTP API 查询。

### 3.4 Redis

- **容器**：`redis`
- **URL**（容器内）：`redis://redis:6379/0`（若设 `REDIS_PASSWORD` 需带密码）
- **用途**：
  - Celery broker 与 result backend
  - 平台缓存（如知识库 scope 树）
  - 在线状态（`online_presence`）

Redis 以 **键值** 存储，无固定表结构；任务队列键由 Celery 管理。

### 3.5 MinIO（对象存储）

- **容器**：`minio`
- **S3 端点**（容器内）：`minio:9000`
- **账号**：`.env` 中 `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`（默认 `minioadmin` / `minioadmin`）
- **数据目录**：`${DATA_ROOT}/minio`

| 桶 / 前缀 | 谁写入 | 内容 |
|-----------|--------|------|
| `documents`（平台默认桶） | 平台 API | 用户上传的文档原文件、版本文件 |
| KnowFlow / RAGFlow 相关桶 | RAGFlow 服务 | 解析后的文档块、图片等（与平台共用同一 MinIO 实例） |

### 3.6 其他文件卷

| 目录 | 内容 |
|------|------|
| `data/pdf2zh-config` | BabelDOC 下载的模型与运行时配置 |
| `data/speech-models` | FunASR / ModelScope 语音模型 |
| `data/knowflow-logs` | RAGFlow 容器日志文件 |

---

## 4. 如何连接查看数据

> 生产环境 **不要** 长期将 5432、3306、6379、9000 映射到公网。以下命令均在**服务器本机**或 SSH 会话中执行。

### 4.1 PostgreSQL

```bash
# 进入交互式 psql
docker compose -p zhitan exec -it postgres \
  psql -U platform -d platform

# 常用查询示例
# \dt                          -- 列出所有表
# SELECT id, title FROM documents LIMIT 10;
# SELECT id, type, status FROM jobs ORDER BY created_at DESC LIMIT 20;
```

一次性导出（与 backup 相同逻辑）：

```bash
docker compose -p zhitan exec -T postgres \
  pg_dump -U platform platform | gzip > /tmp/platform.sql.gz
```

GUI 工具（DBeaver、pgAdmin）：在 `compose.yaml` 的 `postgres` 服务下**临时**增加 `ports: ["127.0.0.1:5432:5432"]` 后 `stack up`，用 `platform/platform` 连接 `127.0.0.1:5432`；调试完删除该映射并重启栈。**不要**对公网开放数据库端口。

### 4.2 MySQL（KnowFlow）

```bash
docker compose -p zhitan exec -it knowflow-mysql \
  mysql -uroot -p'infini_rag_flow' rag_flow

# 常用查询示例（表名随 RAGFlow 版本可能略有差异）
# SHOW TABLES;
# SELECT id, name FROM knowledgebase LIMIT 10;
# SELECT id, name, status FROM document LIMIT 10;
```

密码以 `.env` 中 `MYSQL_PASSWORD` 为准。

### 4.3 Redis

```bash
# 无密码时
docker compose -p zhitan exec -it redis redis-cli

# 有 REDIS_PASSWORD 时
docker compose -p zhitan exec -it redis redis-cli -a "$REDIS_PASSWORD"

# 示例
# KEYS platform:*          -- 平台缓存键（前缀因版本而异）
# LLEN celery               -- Celery 队列长度（键名以实际为准）
```

### 4.4 MinIO

**方式 A：容器内 mc 客户端**

```bash
docker compose -p zhitan exec -it minio sh -c '
  mc alias set local http://127.0.0.1:9000 minioadmin minioadmin
  mc ls local/
  mc ls local/documents/
'
```

将 `minioadmin` 替换为 `.env` 中实际账号。

**方式 B：临时开放 Console（仅本机调试）**

```bash
docker compose -p zhitan run --rm -p 127.0.0.1:9001:9001 --no-deps minio \
  server /data --console-address ":9001"
```

浏览器访问 http://127.0.0.1:9001 ，用 `MINIO_ROOT_*` 登录。

### 4.5 Infinity

Infinity 无 SQL 登录界面，用 HTTP 检查节点状态：

```bash
docker compose -p zhitan exec -it ragflow-infinity \
  curl -fsS http://127.0.0.1:23820/admin/node/current
```

业务数据通过 **RAGFlow API**（`http://ragflow:9380`，平台经 `RAGFLOW_API_URL` 调用）或平台「知识检索」功能查看，不要直接删 `${DATA_ROOT}/knowflow-infinity` 目录（会丢失全部向量索引）。

### 4.6 平台内可视化（无需直连数据库）

| 场景 | 入口 |
|------|------|
| 文档与权限 | Web → 文档中心 |
| 后台任务 | Web → 任务面板 / `GET /api/v1/jobs` |
| KnowFlow 切片与知识库 | Web → 切片管理（iframe） |
| 系统监控 | 系统设置 → 监控（需管理员） |
| 用户与部门 | 系统设置 → 用户 / 部门 |

---

## 5. 数据流简图

```mermaid
flowchart TB
  subgraph platform["平台控制面"]
    API["api / worker"]
    PG[("PostgreSQL\n元数据·权限·任务")]
  end

  subgraph objects["对象与队列"]
    MN["MinIO\n文件二进制"]
    RD[("Redis\n队列·缓存")]
  end

  subgraph knowflow["KnowFlow profile"]
    MY[("MySQL rag_flow\nRAG 元数据")]
    INF["Infinity\n向量·全文"]
    RF["ragflow-server"]
  end

  API --> PG
  API --> MN
  API --> RD
  WRK["worker"] --> PG
  WRK --> MN
  API -->|同步索引| RF
  RF --> MY
  RF --> INF
  RF --> MN
```

---

## 6. 相关文档

| 文档 | 说明 |
|------|------|
| [Docker 容器说明](docker-services.md) | 健康检查、profile、开发差异 |
| [数据库迁移](database-migration.md) | schema_migrate、备份恢复 |
| [配置说明](configuration.md) | `.env` 变量 |
| [功能实现说明](feature-implementation.md) | 各功能数据流（无代码） |
| [运维部署指南](../../../运维部署指南.md) | 启动、部署、端口速查 |
