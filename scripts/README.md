# 脚本说明

仓库根目录下 `scripts/` 的入口脚本一览。均在**仓库根目录**执行：`bash scripts/<name>.sh`。

## 本地开发与运行

| 脚本 | 作用 |
|------|------|
| `start_platform.sh` | 启动智碳平台（默认 `local`：基础设施 Docker + 宿主机 API/Worker/前端）。模式：`local` / `speech` / `knowflow` / `docker` / `docker-full` |
| `stop_platform.sh` | 停止平台相关进程与 Compose 栈 |
| `download_babeldoc_assets.sh` | 下载 PDF 翻译所需 BabelDOC 模型与字体（首次） |
| `start_speech_local.sh` | 在宿主机启动语音转写（一般用 `start_platform.sh speech` 即可） |

## amd64 生产部署（目标机 Linux x86_64）

| 脚本 | 作用 |
|------|------|
| `deploy_amd64.sh` | 在目标机一键 Docker 部署。子命令：`core` / `knowflow` / `speech` / `full` / `down` |
| `push_and_deploy.sh` | 本机 SSH + rsync 同步到 `platform/deploy.target.amd64`，远程执行 `deploy_amd64.sh` |
| `pack_deploy_bundle.sh` | 打包 `dist/pdf_trans-deploy-*.tar.gz`（内网/无 git 场景） |
| `ensure_local_env.sh` | Mac 本地：把误写成 `postgres/redis` 的 `.env` 改回 `127.0.0.1` |
| `sync_deploy_env.sh` | amd64：生成 `.env.docker`（**不修改**本地 `.env`） |

详见 [amd64 部署指南](../docs/zh/development/deploy-amd64.md)。

## KnowFlow / RAGFlow（Apple Silicon 从源码构建）

| 脚本 | 作用 |
|------|------|
| `setup_knowflow.sh` | 克隆 KnowFlow 到 `platform/third_party/KnowFlow` |
| `download_knowflow_deps_light.sh` | 下载 RAGFlow LIGHTEN 构建依赖（由 `build_knowflow_source.sh` 调用） |
| `build_knowflow_source.sh` | 构建 deps + RAGFlow + KnowFlow Server 镜像（首次约 30–90 分钟） |
| `build_knowflow_server_only.sh` | 仅重建 `knowflow-server:source`（RAGFlow 镜像已存在时） |
| `check_knowflow.sh` | 检查 KnowFlow/RAGFlow HTTP 栈是否可达 |
| `test_knowflow_integration.sh` | 集成冒烟：pytest + HTTP + embed-session（需栈已启动） |

amd64 服务器请用 `deploy_amd64.sh knowflow`（预构建镜像），勿跑源码构建。

## 语音转写

| 脚本 | 作用 |
|------|------|
| `setup_speech.sh` | 首次构建 `speech-api` Docker，模型落到 `.run/speech-models/` |

## 维护

| 脚本 | 作用 |
|------|------|
| `cleanup_docker_unused.sh` | 清理已退出无关容器、旧 KnowFlow 预构建镜像、悬空层（保留运行中 platform/knowflow 栈） |
