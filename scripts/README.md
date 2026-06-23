# 脚本说明

**唯一开发入口：`./dev.sh`**（实现位于 `scripts/dev.sh`）。

## 分类

| 类别 | 脚本 | 说明 |
|------|------|------|
| **入口** | `dev.sh`（根目录 `./dev.sh` 转发） | 本机 / Docker 开发、remote-dev、stack / deploy 透传 |
| **本机开发** | `local-dev.sh` | API :8000 + Vite :40005 + Worker（由 `./dev.sh local` 调用） |
| **容器编排** | `stack.sh`、`deploy.sh` | Compose build / up / backup；生产镜像部署 |
| **环境** | `setup-env.sh`、`setup-stack-env.sh` | `platform/.env`（remote-dev / 本机 PG）；根 `.env` 合并 |
| **数据迁移** | `migrate-postgres.sh` | 平台库 remote ↔ 本机 Docker postgres |
| **远程依赖** | `verify-remote-deps.sh`、`server-deps.sh`、`server-sync.sh`、`server-uninstall-frp.sh` | 端口探测、依赖栈、**代码同步**、卸载 frps |
| **网络暴露** | `dev-frpc.sh`、`frp-server-install.sh` | frp（已废弃，改用 `./dev.sh sync` + `/deps/`） |
| **资源 / 语音** | `download_*.sh`、`start-speech-local.sh` | KnowFlow 构建依赖、BabelDOC 资源、宿主机 speech-api |
| **公共库** | `lib/branding.sh`、`lib/version.sh`、`lib/envfile.sh` | 品牌名、版本号、`.env` 读写 helper |

## `./dev.sh` 常用命令

| 命令 | 说明 |
|------|------|
| `./dev.sh local` | 本机 conda `pdf2zh` API :8000 + Vite :40005 |
| `./dev.sh local status` | 检查 API / 前端 / Worker |
| `./dev.sh local restart` | 重启本机 dev |
| `./dev.sh docker` | 全 Docker 热重载（compose dev-up） |
| `./dev.sh stop` | 停止 Docker 栈 + 本机 dev |
| `./dev.sh remote-dev` | 生成 `REMOTE_DEPS=1` 的 `platform/.env` |
| `./dev.sh sync` | 同步后端到服务器并重启 API / Worker |
| `./dev.sh sync --frontend` | 同步含前端并 npm build + nginx reload（挂载 dist） |
| `./dev.sh browser setup --server` | 在服务器构建 Playwright runtime（浏览器 RPA） |
| `./dev.sh sync --browser` | 同步代码并在服务器重建 Playwright runtime |
| `./dev.sh stack …` | Compose 编排（build / up / logs …） |
| `./dev.sh deploy …` | 生产镜像部署 |
| `./dev.sh db migrate to-local\|to-remote` | 平台 PostgreSQL 迁移 |
| `./dev.sh speech local` | 宿主机 FunASR speech-api（开发 compose 可选） |

## 实现脚本（由 dev.sh 或 stack 调用）

### 环境

```bash
bash scripts/setup-env.sh remote-dev    # 同 ./dev.sh remote-dev
bash scripts/setup-env.sh local-db      # DATABASE_URL → 本机 postgres
bash scripts/setup-stack-env.sh         # stack 缺根 .env 时自动合并
```

### 迁移

```bash
bash scripts/migrate-postgres.sh to-local     # 远程 → 本机
bash scripts/migrate-postgres.sh to-remote    # 本机 → 远程
```

### 远程服务器

```bash
bash scripts/verify-remote-deps.sh
bash scripts/server-deps.sh sync|up|down|status
bash scripts/server-add-swap.sh               # 缓解 OOM
```

## 典型流程

```bash
# 本机开发 + 远程共用数据（推荐）
REMOTE_HOST=172.19.134.45 ./dev.sh remote-dev
bash scripts/verify-remote-deps.sh
./dev.sh local
./dev.sh sync                    # 改代码后推到服务器
./dev.sh sync --frontend         # 含前端

# 服务器首次：见 .env.server.shared.example（全栈 + EXPOSE_DEPS_DB_ONLY + server-up）

# 本机 PG + 远程其余依赖（可选）
bash scripts/migrate-postgres.sh to-local
bash scripts/setup-env.sh local-db
./dev.sh local restart

# 单机全 Docker
./dev.sh docker --profile knowflow --profile speech
```

版本号以根目录 **`VERSION`** 为准。Docker 项目名默认为 `zhitan`（镜像 tag 前缀，非产品名）。
