# amd64 服务器部署

在 **linux/amd64** 上用 Docker 跑全栈（平台 + PDF 翻译 + 可选 KnowFlow / 语音），无需在目标机安装 Python/Node。

部署相关脚本说明见 [scripts/README.md](../../../scripts/README.md)。

## 前置条件

| 项目 | 要求 |
|------|------|
| 系统 | Linux x86_64（Ubuntu 22.04+ / Debian 12+ 等） |
| Docker | 24+，Compose v2（`docker compose version`） |
| 资源 | 建议 ≥ 8GB 内存、≥ 50GB 磁盘 |
| 网络 | Docker Hub / PyPI（或镜像加速） |

## 部署方式对比

| 方式 | 适用 | 入口脚本 |
|------|------|----------|
| **SSH 推送** | 开发机已配置 `platform/deploy.target` | `push_and_deploy.sh` |
| **Git 克隆** | 目标机可拉仓库 | `deploy_amd64.sh` |
| **tar 包** | 内网/无 git | `pack_deploy_bundle.sh` → 目标机 `deploy_amd64.sh` |

## 方式 A：SSH 推送（日常更新推荐）

在 `platform/deploy.target` 中设置 `DEPLOY_HOST`、`DEPLOY_PATH`、`DEPLOY_USER`（示例见仓库内该文件）。

```bash
cd /path/to/pdf_trans
bash scripts/push_and_deploy.sh              # rsync + 远程后台 full 并行部署
bash scripts/push_and_deploy.sh --status     # 查看远程进度
bash scripts/push_and_deploy.sh --push-only  # 只同步代码
bash scripts/push_and_deploy.sh --deploy-only # 只远程部署
```

远程日志：`ssh user@host 'tail -f /path/to/pdf_trans/.run/deploy.log'`

## 方式 B：目标机 Git 克隆

```bash
git clone <仓库地址> pdf_trans && cd pdf_trans
bash scripts/deploy_amd64.sh full    # 或 core / knowflow / speech
bash scripts/deploy_amd64.sh down    # 停止
```

首次构建 pdf2zh 镜像约 15–40 分钟；KnowFlow 拉预构建镜像约 5–15 分钟。

## 方式 C：离线 tar 包

开发机：

```bash
bash scripts/pack_deploy_bundle.sh
# dist/pdf_trans-deploy-YYYYMMDD-HHMMSS.tar.gz
```

目标机：

```bash
tar xzf pdf_trans-deploy-*.tar.gz && cd pdf_trans
bash scripts/deploy_amd64.sh full
```

## 配置同步

`deploy_amd64.sh` / `push_and_deploy.sh` / `pack_deploy_bundle.sh` 均会调用 `sync_deploy_env.sh`：

- **来源**：本机 `platform/.env`、`platform/knowflow.env`
- **仅改写**：Docker 内网服务名、amd64 KnowFlow 镜像名
- **保持不变**：密码、`DEEPSEEK_*`、Dify Key、RAGFlow 账号等

无本地 `.env` 时回退 `platform/.env.deploy.example`。

## 服务端口

| 服务 | 端口 |
|------|------|
| 平台 Web（Nginx + `/api`） | 80 |
| 平台 API | 8000 |
| pdf2zh API | 7861 |
| MinIO 控制台 | 9001 |
| RAGFlow | 9380 |
| KnowFlow API | 5001 |
| 语音 API | 8765 |

管理员见 `platform/.env` 中 `BOOTSTRAP_ADMIN_*`。

## KnowFlow：amd64 与 arm64

| 架构 | 方式 |
|------|------|
| **amd64** | `deploy_amd64.sh knowflow`（`zxwei/knowflow:v2.1.8` 预构建镜像） |
| Apple Silicon | `build_knowflow_source.sh` + `start_platform.sh knowflow` |

Compose：`platform/docker-compose.knowflow.amd64.yml`、`knowflow.env.amd64.example`。

## 目标机示例（deploy.target）

当前仓库默认目标（可按环境修改 `platform/deploy.target`）：

| 项 | 值 |
|----|-----|
| IP | `172.19.134.45` |
| 路径 | `/root/qzb/zhitanAI` |

访问示例：

| 服务 | URL |
|------|-----|
| 平台 Web | http://172.19.134.45 |
| 平台 API | http://172.19.134.45:8000/docs |
| RAGFlow | http://172.19.134.45:9380 |

防火墙需放行：`80`、`8000`、`7861`、`9380`、`5001`、`8765`（按需 `9000`/`9001`）。

目标机运维：

```bash
cd /root/qzb/zhitanAI
bash scripts/deploy_amd64.sh down
cd platform && docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f api
```

## 日志与排错

```bash
cd platform
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f pdf2zh-api
```

## 相关文件

- `platform/docker-compose.prod.yml` — 生产覆盖
- `platform/.env.deploy.example` — 环境变量模板
- `platform/deploy.target` — SSH 推送目标
- `scripts/deploy_amd64.sh` / `push_and_deploy.sh` / `pack_deploy_bundle.sh`
