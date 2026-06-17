# 部署指南

## 前置条件

- Docker 24+、Docker Compose v2
- 磁盘：KnowFlow + 语音模型建议 **30GB+**
- arm64（Apple Silicon）：KnowFlow 需源码构建或 save/load 镜像
- amd64 服务器：可用 `deploy/knowflow.mirror.yaml` 预构建镜像

## 1. 初始化配置

```bash
cp .env.stack.example .env
# 从 platform/.env.example 复制 JWT_SECRET、DEEPSEEK_API_KEY 等到 .env
bash scripts/stack.sh init-env   # 可选：合并 platform/.env
```

启用 KnowFlow：

```bash
# .env 中
KNOWFLOW_ENABLED=true
STACK_PROFILES="knowflow speech"   # 或 up 时 --profile knowflow
```

## 2. 本地开发

**开发（热重载，推荐）：**

```bash
./dev.sh docker
```

| 模式 | Web | API |
|------|-----|-----|
| `dev.sh docker` | :40005 | :18000 |

KnowFlow 首次启动：Infinity/MySQL 就绪后 ragflow API 约 **1–2 分钟** 可用；若 502：`docker restart ragflow-server`。

> 远程依赖 + 本机 venv 仅为过渡，见 [server-deps.md](server-deps.md)；目标形态为单机 `dev`。

## 3. 本机生产式

```bash
bash scripts/stack.sh build --profile knowflow --profile speech
bash scripts/stack.sh up --profile knowflow --profile speech
```

仅暴露 **40005**。API 文档内网：`docker compose -p zhitan exec api curl -s localhost:8000/health`。

## 4. amd64 / arm64 服务器（镜像交付）

### 4.1 离线 tar 包（同架构 save/load）

**本机（与目标同架构或 buildx）：**

```bash
export ZHITAN_VERSION=4.0.7
bash scripts/stack.sh build --profile knowflow
bash scripts/stack.sh save      # 输出 images/zhitan-*.tar.gz
```

**推送（不 rsync 源码）：**

```bash
cp platform/deploy.target.example platform/deploy.target
bash scripts/deploy.sh stack push
```

### 4.2 阿里云 ACR + 挂载后端源码（推荐）

Python 依赖打进 **`zhitan-api-runtime`** 镜像；`platform/app` 挂载进容器，改代码无需重建镜像。

**1. 本机登录并推送多架构镜像（M1 Mac 可同时推 amd64 + arm64）：**

```bash
# .env 中设置（末尾带 /）
REGISTRY_IMAGE_PREFIX=registry.cn-hangzhou.aliyuncs.com/your-namespace/
INSTALL_PAGEINDEX=1

docker login registry.cn-hangzhou.aliyuncs.com
bash scripts/stack.sh push-registry
```

**2. 服务器快速部署（pull 镜像 + rsync 源码）：**

```bash
# platform/deploy.target
DEPLOY_USE_REGISTRY=1
REGISTRY_IMAGE_PREFIX=registry.cn-hangzhou.aliyuncs.com/your-namespace/

bash scripts/deploy.sh stack push
```

远程将执行：`pull-registry` → `server-up`（API `--reload`，挂载 `./platform/app`）。

**3. 仅本机验证挂载模式：**

```bash
bash scripts/stack.sh build-runtime
bash scripts/stack.sh server-up --profile knowflow
```

| 镜像 | 用途 |
|------|------|
| `zhitan-api-runtime` | 仅 Python 依赖，运行时挂载 `platform/app` |
| `zhitan-api`（production） | 依赖 + 代码 baked-in，用于 `stack save` 离线包 |

---

## 5. 架构对照（原 §4 内容保留）

| 场景 | 构建 | 启动 | 对外端口 |
|------|------|------|----------|
| Mac 开发 | 可选 build | `dev-up` | 40005 + 18000 |
| Linux arm64 生产 | build | `up` | 40005 |
| Linux amd64 生产 | build + mirror 或预构建 KF 镜像 | `deploy.sh stack` | 40005 |

## 6. 已废弃方式

以下 **不再维护**，请勿在新环境使用：

- `platform/docker-compose*.yml` 多文件组合
- `bash scripts/deploy.sh full`（rsync 全仓库 + 远程 build）
- `./dev.sh legacy`（宿主机进程 + 部分 Docker）
- `bash scripts/merge-stack-env.sh`（请用 `setup-stack-env.sh`）

若文档仍引用上述路径，以本页为准。

## 7. KnowFlow 镜像构建（arm64 源码）

```bash
./dev.sh knowflow setup   # 克隆 third_party/KnowFlow
./dev.sh knowflow build   # 30–90 分钟
bash scripts/stack.sh build --profile knowflow
```

服务器 **无需** third_party 目录，仅需 `deploy/knowflow/` + 已 save 的镜像。

## 8. 单机迁移与部署后热重载

- **迁到同一台服务器**（含从 remote-dev 过渡）：见 [单机迁移与热重载](single-server-migration.md)  
- **改代码即生效**：在目标机使用 `./dev.sh docker`（`stack dev-up`），勿用生产 `stack up`  
- **功能实现细节**（无代码）：见 [功能实现说明](feature-implementation.md)
