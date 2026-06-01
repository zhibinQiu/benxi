# 配置文件说明（Mac 本地 vs amd64 服务器）

两套配置**不要混用**。曾把 `.env.docker` 复制到 `.env` 会导致本地 API 连不上数据库。

## Mac M1 本地开发

| 文件 | 用途 |
|------|------|
| `platform/.env.example` | 复制为 `platform/.env` |
| `platform/knowflow.env.example` | 复制为 `platform/knowflow.env` |
| `platform/deploy.target.local` | 说明文件，无敏感信息 |

启动：`bash scripts/start_platform.sh`（会自动执行 `ensure_local_env.sh`）

## Linux amd64 服务器部署

| 文件 | 用途 |
|------|------|
| `platform/.env.amd64.example` | 模板；或由 `sync_deploy_env.sh` 生成 `.env.docker` |
| `platform/knowflow.env.amd64.example` | KnowFlow 预构建镜像 |
| `platform/deploy.target.amd64` | SSH 目标（可从 `deploy.target.example` 复制） |

部署：`bash scripts/push_and_deploy.sh`（**不会**覆盖本机 `.env`）

## 生成物（勿提交 git）

- `platform/.env.docker` / `platform/knowflow.env.docker` — 仅用于 rsync 到服务器
