# 配置说明

## 配置文件一览

| 文件 | 用途 | 提交 Git |
|------|------|----------|
| **`.env`**（仓库根） | 统一栈运行时；compose `env_file` | 否 |
| **`.env.stack.example`** | 栈模板：端口、镜像、profile | 是 |
| **`platform/.env.example`** | 业务密钥与功能开关模板 | 是 |
| **`platform/.env`** | 本地密钥源；可被 merge 进根 `.env` | 通常否 |
| **`platform/deploy.target`** | SSH 部署目标 | 否 |
| **`deploy/knowflow/settings.yaml`** | knowflow-backend 业务配置 | 是 |
| **`compose.yaml`** | 核心服务与环境默认值 | 是 |
| **`compose.dev.yaml`** | 开发覆盖 | 是 |

## 根 `.env` 关键变量

### 栈与镜像

| 变量 | 默认 | 说明 |
|------|------|------|
| `ZHITAN_VERSION` | 3.9.3（见根目录 `VERSION`） | 自有镜像 tag |
| `DATA_ROOT` | ./data | 持久化根目录 |
| `FRONTEND_PORT` | 40005 | 唯一对外 Web 端口 |
| `STACK_USE_MIRROR` | 1 | 启用 compose.mirror.yaml |
| `STACK_PROFILES` | 空 | 如 `knowflow speech` |
| `DOCKER_MIRROR` | docker.1ms.run | Hub 代理 |

### 平台数据库

| 变量 | 说明 |
|------|------|
| `POSTGRES_*` | 平台库账号（compose 注入 `DATABASE_URL`） |
| `MINIO_ROOT_*` | 对象存储；与 KnowFlow 对齐时可改 |

### KnowFlow

| 变量 | 说明 |
|------|------|
| `KNOWFLOW_ENABLED` | 是否启用集成逻辑与 browser 路由 |
| `KNOWFLOW_UI_UPSTREAM_URL` | API 容器内反代上游，**固定** `http://ragflow:80` |
| `KNOWFLOW_UI_PUBLIC_URL` | 浏览器 iframe 基址；生产 `http://host:40005/ragflow-ui`；开发 `http://127.0.0.1:18000/ragflow-ui` |
| `KNOWFLOW_UI_PROXY_PREFIX` | HTML 静态资源前缀；与 PUBLIC_URL 路径一致（见 `knowflow_ui_asset_prefix`） |
| `RAGFLOW_API_URL` | 平台后端调 RAGFlow API：`http://ragflow:9380` |
| `RAGFLOW_ACCOUNT_MODE` | `mapped`（每用户独立）或 `shared` |
| `MYSQL_PASSWORD` / `ELASTIC_PASSWORD` | KnowFlow 栈密码 |

### 业务（见 platform/.env.example）

- `JWT_SECRET` — **生产必改**
- `DEEPSEEK_API_KEY` — 会议总结、部分 LLM
- `BOOTSTRAP_ADMIN_PHONE` / `PASSWORD` — 首次管理员
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
