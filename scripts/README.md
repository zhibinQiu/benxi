# 脚本说明

**唯一入口：`./dev.sh`**（仓库根目录，实现位于 `scripts/dev.sh`）。

## 命令

| 命令 | 说明 |
|------|------|
| `./dev.sh local` | 本机 venv API :8000 + Vite :40005 |
| `./dev.sh local status` | 检查 API / 前端 / Worker |
| `./dev.sh local restart` | 重启本机 dev |
| `./dev.sh docker` | 全 Docker 热重载（compose dev-up） |
| `./dev.sh stop` | 停止 Docker 栈 + 本机 dev |
| `./dev.sh remote-dev` | 生成 `REMOTE_DEPS=1` 的 `platform/.env` |
| `./dev.sh stack …` | Compose 编排（build / up / logs …） |
| `./dev.sh deploy …` | 生产镜像部署 |
| `./dev.sh knowflow setup` | 克隆 KnowFlow 源码 |

## 实现脚本（由 dev.sh 调用，勿记）

| 脚本 | 职责 |
|------|------|
| `scripts/local-dev.sh` | 本机 API / Vite / Worker 启停 |
| `scripts/stack.sh` | Docker Compose 编排 |
| `scripts/deploy.sh` | 远程镜像部署 |
| `scripts/setup-remote-dev-env.sh` | remote-dev 用 `.env` |
| `scripts/setup-stack-env.sh` | 合并 `platform/.env` → 根 `.env` |
| `scripts/verify-remote-deps.sh` | 探测远程依赖端口 |
| `scripts/migrate-postgres-to-remote.sh` | 本机 PG 数据导入远程 40002 |
| `scripts/migrate-postgres-to-local.sh` | 远程 PG 数据导入本机 |
| `scripts/setup-local-db-env.sh` | 切换为本机 PostgreSQL |
| `scripts/server-deps.sh` | 远程服务器同步依赖栈 |
| `scripts/server-add-swap.sh` | 远程服务器添加 Swap |

## 典型流程

```bash
# 本机开发 + 远程 Redis/MinIO/KnowFlow
REMOTE_HOST=172.19.134.45 ./dev.sh remote-dev
bash scripts/verify-remote-deps.sh
./dev.sh local

# 单机全 Docker
./dev.sh docker --profile knowflow --profile speech
```

版本号以根目录 **`VERSION`** 为准。Docker 项目名默认为 `zhitan`（镜像 tag 前缀，非产品名）。
