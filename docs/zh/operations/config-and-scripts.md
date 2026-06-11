# 配置文件与脚本说明（v3.9.3）

> 本文说明当前系统**仍在使用**的 Compose 编排文件、环境配置与脚本职责。  
> 数据存储与数据库连接见 [组件位置与数据存储](components-and-storage.md)。

---

## 1. Compose 编排文件

当前**仅**使用仓库根目录的统一栈，**不存在** `platform/docker-compose*.yml`（已删除）。

### 1.1 文件清单与合并顺序

`scripts/stack.sh` 按以下顺序叠加（后者覆盖前者）：

| 顺序 | 文件 | 何时叠加 | 作用 |
|------|------|----------|------|
| 1 | **`compose.yaml`** | 始终 | 核心服务：postgres、redis、minio、pdf2zh-api、api、worker、frontend；speech-api（profile） |
| 2 | **`compose.mirror.yaml`** | `STACK_USE_MIRROR=1`（默认） | 国内 Docker Hub 镜像前缀与 build args |
| 3 | **`deploy/knowflow.yml`** | `--profile knowflow` | MySQL、Infinity、Gotenberg、ragflow、knowflow-backend |
| 4 | **`deploy/knowflow.mirror.yaml`** | 镜像加速 + knowflow profile | KnowFlow 预构建镜像（amd64 常用） |
| 5 | **`compose.dev.yaml`** | `stack.sh dev-up` | API 热重载、Vite 前端、挂载源码 |
| 6 | **`compose.expose-deps.yaml`** | `EXPOSE_DEPS=1` | 映射 40002–40009 供 remote-dev |

```mermaid
flowchart LR
  BASE["compose.yaml"]
  MIR["compose.mirror.yaml"]
  KF["deploy/knowflow.yml"]
  KFM["deploy/knowflow.mirror.yaml"]
  DEV["compose.dev.yaml"]
  EXP["compose.expose-deps.yaml"]

  BASE --> MIR
  MIR --> KF
  KF --> KFM
  KFM --> DEV
  KFM --> EXP
```

### 1.2 各文件详解

#### `compose.yaml` — 基础栈

- **项目名**：`zhitan`（`COMPOSE_PROJECT_NAME` 可覆盖，远程依赖栈常用 `lvye`）
- **对外端口**：仅 `frontend` → `${FRONTEND_PORT:-40005}`
- **数据卷**：`${DATA_ROOT}/postgres|minio|pdf2zh-config|speech-models`
- **容器间地址**：`api` 环境变量写死 Docker DNS（`postgres:5432`、`minio:9000` 等）

#### `compose.dev.yaml` — 开发热重载

| 服务 | 变更 |
|------|------|
| `api` | 映射 `127.0.0.1:18000:8000`；`uvicorn --reload`；挂载 `platform/app`、`docs/` |
| `worker` | 挂载 `platform/app`、`workers` |
| `frontend` | 换用 `node:22` + Vite；`VITE_API_BASE=http://127.0.0.1:18000` |

入口：`bash scripts/zhitan.sh dev`

#### `compose.mirror.yaml` — 国内镜像

覆盖 postgres/redis/minio 等 `image:` 与 Dockerfile `build.args`，避免直连 Docker Hub。

变量：`DOCKER_MIRROR`（默认 `docker.1ms.run`）、`PIP_INDEX_URL`、`NPM_REGISTRY`。

#### `compose.expose-deps.yaml` — 远程依赖端口

仅在服务器跑依赖、本机跑 API 时使用。映射 postgres:40002、redis:40003 … knowflow-mysql:40009。  
模板：`.env.server.deps.example`。

#### `deploy/knowflow.yml` — KnowFlow profile

| 服务 | 职责 |
|------|------|
| `knowflow-mysql` | RAGFlow 元数据（库 `rag_flow`） |
| `knowflow-infinity` | 向量与全文索引（`DOC_ENGINE=infinity`） |
| `knowflow-gotenberg` | Office → PDF |
| `ragflow` | RAGFlow Web + API（容器内 nginx :80，后端 :9380） |
| `knowflow-backend` | KnowFlow 管理 API :5000 |

挂载：`deploy/knowflow/nginx/*`、`infinity_conf.toml`、`settings.yaml`、`theme/*`。

#### `deploy/knowflow.mirror.yaml` — KnowFlow 镜像加速

amd64 生产常用预构建：`zxwei/knowflow:v2.1.8`、`zxwei/knowflow-server:v2.1.8`。

### 1.3 已删除 / 废弃的 Compose 方式

| 废弃项 | 替代 |
|--------|------|
| `platform/docker-compose.yml` 等 | 根目录 `compose.yaml` |
| `docker-compose.knowflow.yml` | `deploy/knowflow.yml` |
| `docker-compose.speech.yml` | `compose.yaml` 内 `speech-api` profile |
| `compose.server-deps.yaml`（空文件） | `compose.expose-deps.yaml` + `stack.sh` |
| `merge-stack-env.sh` | `setup-stack-env.sh` |

---

## 2. 环境配置文件

| 文件 | 用途 | 提交 Git |
|------|------|----------|
| **`VERSION`** | 单一版本源 → `ZHITAN_VERSION` 镜像 tag | 是 |
| **`.env`** | 栈运行时（compose `env_file`） | 否 |
| **`.env.stack.example`** | 栈模板：端口、镜像、profile、KnowFlow 开关 | 是 |
| **`.env.server.deps.example`** | 远程依赖服务器 `.env` 模板（含 `EXPOSE_DEPS=1`） | 是 |
| **`platform/.env`** | 业务密钥源（JWT、API Key、管理员） | 通常否 |
| **`platform/.env.example`** | 业务配置模板 | 是 |
| **`platform/.env.remote.example`** | remote-dev 本机 `.env` 模板 | 是 |
| **`platform/deploy.target`** | SSH 部署目标（`DEPLOY_HOST`、`DEPLOY_PATH`） | 否 |
| **`deploy/knowflow/settings.yaml`** | knowflow-backend 运行时配置 | 是 |
| **`deploy/knowflow/infinity_conf.toml`** | Infinity 向量库配置 | 是 |
| **`deploy/knowflow/init.sql`** | MySQL 首次初始化（库 `rag_flow`） | 是 |

### 生成 `.env`

```bash
cp .env.stack.example .env
cp platform/.env.example platform/.env
# 编辑 JWT_SECRET、BOOTSTRAP_ADMIN_* 等
bash scripts/setup-stack-env.sh   # 合并 platform/.env → 根 .env
```

关键变量见 [配置说明](configuration.md)。

---

## 3. 脚本说明

日常开发优先 **`zhitan.sh`**；Docker 编排实现为 **`stack.sh`**。

### 3.1 入口脚本

| 脚本 | 职责 | 常用命令 |
|------|------|----------|
| **`scripts/zhitan.sh`** | 开发运维统一入口（薄包装） | `dev`、`stop`、`remote-dev`、`local-dev`、`knowflow setup` |
| **`scripts/stack.sh`** | Compose 编排唯一实现 | `build`、`up`、`dev-up`、`down`、`save`、`load`、`backup` |
| **`scripts/deploy.sh`** | 生产镜像推送（仅 stack 模式） | `stack push`、`local stack` |

### 3.2 配置与环境

| 脚本 | 职责 |
|------|------|
| **`setup-stack-env.sh`** | 将 `platform/.env` 合并到根 `.env`；缺 `.env` 时从模板创建 |
| **`setup-remote-dev-env.sh`** | 根据 `platform/.env.remote.example` 生成 `REMOTE_DEPS=1` 的 `platform/.env` |
| **`verify-remote-deps.sh`** | 探测远程服务器 40002–40009 端口与健康 |

### 3.3 远程依赖（过渡）

| 脚本 | 职责 |
|------|------|
| **`server-deps.sh`** | 同步编排到远程服务器；`EXPOSE_DEPS=1` + `stack.sh up` 启动依赖栈 |

### 3.4 辅助脚本

| 脚本 | 职责 |
|------|------|
| **`lib/version.sh`** | 读取根 `VERSION` |
| **`lib/local-dev.sh`** | 本机 venv API + Vite + Celery（`zhitan.sh local-dev` 调用） |
| **`start_speech_local.sh`** | 宿主机 FunASR（dev 时 API 指向 `host.docker.internal:8765`） |
| **`download_babeldoc_assets.sh`** | 下载 BabelDOC 翻译资源 |
| **`download_knowflow_deps_light.sh`** | KnowFlow 源码构建依赖（`zhitan knowflow build`） |

### 3.3 命令对照

```bash
# 开发（推荐）
bash scripts/zhitan.sh dev
# ≡ bash scripts/stack.sh dev-up --profile knowflow --profile speech

# 生产式本机
bash scripts/stack.sh build --profile knowflow --profile speech
bash scripts/stack.sh up --profile knowflow --profile speech

# 远程依赖服务器
cp .env.server.deps.example .env
EXPOSE_DEPS=1 bash scripts/stack.sh up --profile knowflow --profile speech \
  postgres redis minio knowflow-mysql knowflow-infinity knowflow-gotenberg ragflow knowflow-backend

# 生产部署
bash scripts/stack.sh build --profile knowflow --profile speech
bash scripts/stack.sh save
bash scripts/deploy.sh stack push
```

---

## 4. 文档站 Mermaid 图表

运维文档中的架构图使用 [Mermaid](https://mermaid.js.org/) 语法。本地预览：

```bash
pip install -r docs/requirements-docs.txt
mkdocs serve -a 127.0.0.1:8765
```

配置要点（`mkdocs.yml`）：

- 使用 **Material 主题内置 Mermaid**（`pymdownx.superfences` + `fence_code_format`）
- **不要**再安装 `mkdocs-mermaid2-plugin`（与 Material 冲突会导致图表不渲染）
- 须通过 `mkdocs serve` 或 `mkdocs build` 后由 HTTP 服务访问，**不要**直接双击 `index.html` 打开

---

## 5. 相关文档

| 文档 | 说明 |
|------|------|
| [运维部署指南](../../../运维部署指南.md) | 启动、部署、端口速查 |
| [Docker 容器说明](docker-services.md) | 各容器职责与健康检查 |
| [配置说明](configuration.md) | `.env` 变量详解 |
| [scripts/README.md](../../../scripts/README.md) | 脚本速查 |
