# amd64 服务器部署

在 **linux/amd64** 上用 Docker 跑全栈（平台 + PDF 翻译 + 可选 KnowFlow / 语音），无需在目标机安装 Python/Node。

日常只需两个脚本：**本地 `zhitan.sh`**、**远程 `deploy.sh`**（见 [scripts/README.md](../../../scripts/README.md)）。

## 前置条件

| 项目 | 要求 |
|------|------|
| 系统 | Linux x86_64（Ubuntu 22.04+ / Debian 12+ 等） |
| Docker | 24+，Compose v2（`docker compose version`） |
| 资源 | 建议 ≥ 8GB 内存、≥ 50GB 磁盘 |
| 网络 | Docker Hub / PyPI（或镜像加速） |

## 配置（三份模板）

| 文件 | 用途 |
|------|------|
| `platform/.env.example` | 复制为 `.env`（本地与部署源） |
| `platform/knowflow.env.example` | 复制为 `knowflow.env`（含 amd64 预构建镜像注释） |
| `platform/deploy.target.example` | 复制为 `deploy.target`（SSH，勿提交密码） |

部署时 `deploy.sh` 会生成 **勿提交** 的 `.env.docker`、`knowflow.env.docker`。

## 部署方式对比

| 方式 | 适用 | 入口 |
|------|------|------|
| **SSH 推送** | 日常 | `bash scripts/deploy.sh` 或 `bash scripts/zhitan.sh deploy` |
| **Git 克隆** | 目标机可拉仓库 | `deploy.sh local full` |
| **tar 包** | 内网/无 git | `pack_deploy_bundle.sh` → `deploy.sh local full` |

## 方式 A：SSH 推送（推荐）

```bash
cp platform/deploy.target.example platform/deploy.target
# 编辑 DEPLOY_HOST、DEPLOY_PATH、DEPLOY_USER

bash scripts/deploy.sh                       # rsync + 远程 app
bash scripts/deploy.sh full                  # 首次或大改
bash scripts/deploy.sh --status
```

`DEPLOY_ARCH=auto` 时按目标机 `uname -m` 选择 amd64 预构建镜像或 arm64 源码构建。

### 日常 vs 全量

| 模式 | 命令 | 行为 |
|------|------|------|
| **app**（默认） | `deploy.sh` | 只 build/up 应用容器 |
| **core** | `deploy.sh local core` | 含 postgres/redis/minio |
| **full** | `deploy.sh full` | KnowFlow + 语音 + 核心 |

## 方式 B：目标机 Git 克隆

```bash
git clone <仓库地址> pdf_trans && cd pdf_trans
bash scripts/deploy.sh local full
```

## 方式 C：离线 tar 包

```bash
bash scripts/pack_deploy_bundle.sh
# 目标机解压后：
bash scripts/deploy.sh local full
```

## 配置同步

推送前 `deploy.sh` 内嵌 `sync_deploy_env`：

- **来源**：本机 `platform/.env`、`knowflow.env`（缺失则回退 `.env.example` / `knowflow.env.example`）
- **改写**：Docker 内网服务名；amd64 时写入 `zxwei/knowflow:v2.1.8` 等
- **不改**：密码、API Key、RAGFlow 账号等

## 服务端口

| 服务 | 端口 |
|------|------|
| 平台 Web | 40005（`FRONTEND_PORT`） |
| 平台 API | 8000 |
| pdf2zh API | 7861 |
| RAGFlow | 9380 |
| KnowFlow API | 5001 |
| 语音 API | 8765 |

## KnowFlow：amd64 与 arm64

| 架构 | 方式 |
|------|------|
| **amd64 Linux** | `deploy.sh full`（预构建镜像，见 `knowflow.env.example` 注释段） |
| **arm64 Linux** | `deploy.sh full`（源码构建，首次较慢） |
| Apple Silicon | `zhitan.sh knowflow build` + `zhitan.sh knowflow` |

Compose：`docker-compose.knowflow.yml` / `docker-compose.knowflow.amd64.yml`（按架构 include）。

## 目标机运维

```bash
bash scripts/deploy.sh local down
cd platform && docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f api
```

## 相关文件

- `platform/docker-compose.prod.yml`
- `platform/.env.example`、`knowflow.env.example`、`deploy.target.example`
- `scripts/deploy.sh`、`scripts/zhitan.sh`
