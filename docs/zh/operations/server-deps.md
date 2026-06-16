# 远程依赖开发（过渡方案）

> **说明**：在依赖已迁到 **同一台服务器** 前，可用本模式：服务器跑 Postgres / Redis / MinIO / KnowFlow 等，本机只跑 API + 前端 +（按需）Worker。  
> **最终目标**见 [单机迁移与热重载](single-server-migration.md)。

---

## 1. 架构

```mermaid
flowchart LR
  DEV[开发者本机]
  LOCAL["API :8000 + Vite :40005 + Worker 可选"]
  REMOTE["服务器 40002-40009"]

  DEV --> LOCAL
  LOCAL --> REMOTE
```

| 位置 | 运行内容 |
|------|----------|
| 服务器 | `postgres` `redis` `minio` `pdf2zh` `speech` `knowflow` 全栈，**EXPOSE_DEPS=1** 映射 40002–40009 |
| 本机 | FastAPI（venv）、Vite、Celery Worker（远程 Redis 无 Worker 时自动启动） |

---

## 2. 服务器侧

```bash
# 同步编排（可选，见 server-deps.sh）
bash scripts/server-deps.sh sync
bash scripts/server-deps.sh up

# 或已有仓库时
EXPOSE_DEPS=1 bash scripts/stack.sh up --profile knowflow --profile speech
```

端口约定见 `compose.expose-deps.yaml` 与 `.env.server.deps.example`。

---

## 3. 本机侧

```bash
REMOTE_HOST=172.19.134.45 ./dev.sh remote-dev
bash scripts/verify-remote-deps.sh
./dev.sh local
./dev.sh local status
```

`./dev.sh remote-dev`（或 `bash scripts/setup-env.sh remote-dev`）根据 `platform/.env.remote.example` 生成 `platform/.env`（`REMOTE_DEPS=1`）。

### 3.1 混合模式：本机 PostgreSQL + 远程其余依赖

远程 `40002` 不稳定时，可将**平台业务库**迁到本机，Redis / MinIO / KnowFlow 仍走远程：

```bash
# 远程可用时先迁数据（可选；失败可沿用本机 data/postgres 已有快照）
bash scripts/migrate-postgres.sh to-local

# 改 platform/.env 的 DATABASE_URL → 127.0.0.1:5432，保留 REMOTE_DEPS=1
bash scripts/setup-env.sh local-db

docker compose -f compose.yaml -f compose.local-db.yaml up -d postgres
./dev.sh local restart
curl -s http://127.0.0.1:8000/health   # 期望 {"ok":true,"db":true,...}
```

文档二进制仍在远程 MinIO；`ragflow_*_links` 等映射在 PG 中，从 dump 恢复后与远程 KnowFlow 实例 ID 一致。

---

## 4. 热重载（本机）

| 组件 | 行为 |
|------|------|
| 前端 | 保存即 Vite HMR |
| API | uvicorn `--reload` |
| Worker | 改任务代码后重启 local worker 进程 |

本机 **所见即所得**；服务器上 KnowFlow/pdf2zh 等仍为容器，改平台代码不 rebuild 远程镜像。

---

## 5. 迁到单机

完成联调后按 [单机迁移与热重载](single-server-migration.md)：

1. `stack backup`  
2. 目标机 `stack up`（无 EXPOSE_DEPS）  
3. `stack restore`  
4. `platform/.env` 改为 Docker 服务名  
5. 服务器上使用 `dev.sh docker` 继续热重载  

---

## 相关命令

| 命令 | 说明 |
|------|------|
| `bash scripts/server-deps.sh status` | 查看远程容器 |
| `bash scripts/server-deps.sh down` | 停远程依赖（不影响同机 Dify 等） |
| `bash scripts/verify-remote-deps.sh` | 本机探测 40002–40009 |
