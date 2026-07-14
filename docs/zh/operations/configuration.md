# 配置说明

> Compose 文件合并顺序、脚本职责、Mermaid 文档配置见 **[配置文件与脚本](config-and-scripts.md)**。

## 配置文件一览

| 文件 | 用途 | 提交 Git |
|------|------|----------|
| **`.env`**（仓库根） | 统一栈运行时；compose `env_file` | 否 |
| **`configs/envs/.env.stack.example`** | 栈模板：端口、镜像、profile | 是 |
| **`configs/envs/.env.server.deps.example`** | 远程依赖服务器模板（`EXPOSE_DEPS=1`） | 是 |
| **`platform/.env.example`** | 业务密钥与功能开关模板 | 是 |
| **`platform/.env.remote.example`** | remote-dev 本机模板 | 是 |
| **`platform/.env`** | 本地密钥源；可被 merge 进根 `.env` | 通常否 |
| **`platform/deploy.target`** | SSH 部署目标 | 否 |
| **`third_party/deploy/knowflow/settings.yaml`** | knowflow-backend 业务配置 | 是 |
| **`configs/compose/compose.yaml`** | 核心服务（基础编排） | 是 |
| **`configs/compose/compose.dev.yaml`** | 开发热重载覆盖 | 是 |
| **`configs/compose/compose.server.yaml`** | 服务器挂载源码覆盖 | 是 |
| **`configs/compose/compose.mirror.yaml`** | 国内镜像加速 | 是 |
| **`configs/compose/compose.expose-deps.yaml`** | 远程依赖端口映射 | 是 |
| **`configs/compose/compose.sandbox.yaml`** | Skill 沙箱执行器 | 是 |
| **`third_party/deploy/knowflow.yml`** | KnowFlow profile 服务 | 是 |

## 根 `.env` 关键变量

### 栈与镜像

| 变量 | 默认 | 说明 |
|------|------|------|
| `BENXI_VERSION` | 4.6.0（见根目录 `VERSION`） | 自有镜像 tag |
| `DATA_ROOT` | ./data | 持久化根目录 |
| `FRONTEND_PORT` | 40005 | 唯一对外 Web 端口 |
| `STACK_USE_MIRROR` | 1 | 启用 compose.mirror.yaml |
| `STACK_PROFILES` | 空 | 如 `knowflow speech` |
| `DOCKER_MIRROR` | docker.1ms.run | Hub 代理 |

### 平台数据库

| 变量 | 说明 |
|------|------|
| `POSTGRES_*` | 平台库账号（compose 注入 `DATABASE_URL`） |
| `DATABASE_READ_URL` | 可选只读副本；留空则读写均走 `DATABASE_URL` |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | SQLAlchemy 连接池（主库与副本各自独立池）；**生产单机默认见下方档位 C** |
| `MINIO_ROOT_*` | 对象存储；与 KnowFlow 对齐时可改 |

### 单机生产档位 C（200 在线 / 瞬时 ~100–150 打 DB）

`compose.yaml` 与 `compose.server.yaml` 已内置下列值（**覆盖** `platform/.env` 中同名变量）。本地 `dev.sh local` 仍用 `platform/.env` 的 20/20。

| 组件 | 配置 | PG 连接预算 |
|------|------|-------------|
| **postgres** | `max_connections=220`，`shared_buffers=512MB` | 上限 220 |
| **api** | uvicorn `--workers 6`，`mem_limit 4g` | 6×(12+8)=**120** |
| **api 环境** | `DB_POOL_SIZE=12`，`DB_MAX_OVERFLOW=8`，`DB_POOL_TIMEOUT=15` | 同上 |
| **api 流式** | `STREAM_MAX_CONCURRENT_PER_WORKER=12`，`STREAM_ACQUIRE_TIMEOUT=5` | 每 worker 独立计数 |
| **worker** | Celery `--concurrency 12` | 1×(10+5)=**15** |
| **worker 环境** | `DB_POOL_SIZE=10`，`DB_MAX_OVERFLOW=5` | 同上 |

应用后重启：

```bash
./dev.sh sync              # 服务器：同步后端 + 重建 API/Worker（含档位 C）
./dev.sh sync --all        # 同上 + 前端 build + nginx reload
./dev.sh local restart     # 本机：重启 API + Vite + Worker
```

或手动：

```bash
bash scripts/stack.sh restart api worker   # 若 stack 支持
bash scripts/stack.sh up -d --force-recreate postgres api worker
```

压测（需 API 已启动）：

```bash
cd platform
python scripts/stress_test_throughput.py --concurrency 80 --parse-jobs 80
```

硬件建议：**≥8 核 CPU、≥16GB RAM**（含 KnowFlow profile 时建议 32GB）。

### KnowFlow

| 变量 | 说明 |
|------|------|
| `KNOWFLOW_ENABLED` | 是否启用 RAGFlow API / knowflow-backend 集成 |
| `KNOWFLOW_BACKEND_URL` | knowflow-backend 扩展 API（容器内 `http://knowflow-backend:5000`） |
| `RAGFLOW_API_URL` | 平台后端调 RAGFlow API（容器内 `http://ragflow:80` 或 `:9380`） |
| `RAGFLOW_ACCOUNT_MODE` | `mapped`（每用户独立）或 `shared` |
| `MYSQL_PASSWORD` | KnowFlow MySQL 密码 |
| `DOC_ENGINE` | 向量库引擎，固定 `infinity` |
| `INFINITY_VERSION` | Infinity 镜像版本（默认 `v0.6.0-dev5`） |

### 业务（见 platform/.env.example）

- `JWT_SECRET` — **生产必改**
- `DEEPSEEK_API_KEY` — 会议总结、部分 LLM
- `BOOTSTRAP_ADMIN_PHONE` / `PASSWORD` — 首次管理员（默认 `admin` / `admin123`）
- `DESIGN_SYSTEM_UPSTREAM_URL` — 智能问数 iframe
- `SPEECH_SERVICE_URL` — 容器内 `http://speech-api:8765`

## compose 内硬编码（一般勿改）

`compose.yaml` 的 `api.environment` 将容器间地址写死为 Docker DNS 名；仅 `KNOWFLOW_*`、`KNOWFLOW_ENABLED` 等从 `.env` 覆盖。

## 生成 .env

```bash
bash scripts/setup-stack-env.sh    # stack.sh init-env / 缺 .env 时自动调用
cp .env.stack.example .env         # 手动
```

## 前端构建参数

| 变量 | 生产 | 开发 |
|------|------|------|
| `VITE_BASE_PATH` | /ai/ | /ai/ |
| `VITE_API_BASE` | /ai | http://127.0.0.1:18000 |

生产构建在 `platform-frontend/Dockerfile`；开发由 `compose.dev.yaml` 注入。
