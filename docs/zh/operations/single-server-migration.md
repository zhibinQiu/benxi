# 单机迁移与热重载部署（v4.0.7）

> **目标**：将当前「本机开发 + 远程依赖」或「多机拆分」架构，迁移到 **同一台服务器** 运行完整栈；并在部署后仍支持 **改代码即生效**（所见即所得）。  
> 不含代码，仅操作说明。

---

## 1. 三种运行形态对照

| 形态 | 适用 | 对外端口 | 改代码后 |
|------|------|----------|----------|
| **A. 生产式 `stack up`** | 正式交付、演示 | 仅 **40005** | 需 rebuild 镜像并 restart |
| **B. 开发式 `stack dev-up`** | 服务器上持续迭代 | **40005** + **18000** | API **自动 reload**；前端 **Vite HMR**；Worker 需 **restart** |
| **C. 本机 venv `local-dev`** | 笔记本连远程库（过渡态） | 本机 8000 + 40005 | API reload + Vite HMR；Worker 按需本地 |

**迁移完成后推荐**：在目标服务器长期使用 **形态 B** 做联调与验收；对外发布时再切 **形态 A**。

---

## 2. 从「远程依赖开发」迁到单机

当前常见状态：服务器 `EXPOSE_DEPS=1` 暴露 40002–40009；本机 `REMOTE_DEPS=1` + `./dev.sh local`。

### 2.1 迁移前准备

| 步骤 | 操作 |
|------|------|
| 1 | 在**数据所在服务器**执行 `bash scripts/stack.sh backup`，得到 `backups/YYYYMMDD_HHMMSS/` |
| 2 | 记录当前 `platform/.env` 中 JWT、管理员、LLM Key、KnowFlow 配置 |
| 3 | 确认目标机磁盘 ≥ **30GB**（KnowFlow + 语音模型） |
| 4 | 确认目标机架构（amd64 优先；arm64 需 KnowFlow 源码或预构建镜像） |

### 2.2 在目标服务器部署完整栈（不再 EXPOSE_DEPS）

```bash
# 1. 获取代码与配置
git clone <仓库> /opt/zhitan    # 或 rsync 现有目录
cd /opt/zhitan
cp .env.stack.example .env
cp platform/.env.example platform/.env
# 编辑密钥、KnowFlow、DEEPSEEK 等

# 2. 合并栈环境
bash scripts/stack.sh init-env

# 3. 构建并启动（单机全栈，不暴露 40002 等）
bash scripts/stack.sh build --profile knowflow --profile speech
bash scripts/stack.sh up --profile knowflow --profile speech
# 注意：不要加 compose.expose-deps.yaml（勿设 EXPOSE_DEPS=1）
```

### 2.3 恢复数据

```bash
# 将备份目录拷到目标机 backups/ 下
bash scripts/stack.sh restore backups/20260610_120000
bash scripts/stack.sh up --profile knowflow --profile speech
```

恢复内容通常包括：PostgreSQL 逻辑 dump、MinIO 对象、KnowFlow MySQL（若 profile 启用）。

### 2.4 修改 `platform/.env` 为单机地址

关闭远程依赖模式，改为 **Docker 服务名**（容器内 DNS）：

| 变量 | 单机值（示例） |
|------|----------------|
| `REMOTE_DEPS` | 删除或 `0` |
| `DATABASE_URL` | `postgresql+psycopg2://platform:platform@postgres:5432/platform` |
| `REDIS_URL` | `redis://:密码@redis:6379/0` |
| `MINIO_ENDPOINT` | `minio:9000` |
| `PDF2ZH_API_URL` | `http://pdf2zh-api:7861` |
| `SPEECH_SERVICE_URL` | `http://speech-api:8765` |
| `RAGFLOW_API_URL` | `http://ragflow:80` |
| `KNOWFLOW_BACKEND_URL` | `http://knowflow-backend:5000` |
| `KNOWFLOW_UI_UPSTREAM_URL` | `http://ragflow:80` |
| `KNOWFLOW_UI_PUBLIC_URL` | `http://<服务器IP或域名>:40005/ragflow-ui` 或生产 Nginx 同源路径 |

若 API 跑在容器外（形态 C），将 `postgres` 改为 `127.0.0.1:5432` 且需 compose 映射 postgres 端口或使用 host 网络——**单机推荐形态 B，API 在容器内，无需映射数据库端口**。

### 2.5 停用旧远程暴露栈（可选）

原仅作依赖的服务器若不再需要：

```bash
bash scripts/stack.sh down
# 或远程：bash scripts/server-deps.sh down
```

关闭防火墙上的 40002–40009。

### 2.6 验证

```bash
bash scripts/stack.sh ps
curl -s http://127.0.0.1:40005/ai/ | head
docker compose -p zhitan exec api curl -s localhost:8000/health
```

浏览器访问 `http://<服务器>:40005/ai/`，冒烟：登录 → 上传 → 翻译 → 知识检索。

---

## 3. 单机上的热重载（所见即所得）

### 3.1 推荐：服务器 `stack dev-up`

在服务器仓库目录执行：

```bash
./dev.sh stop          # 停旧进程
./dev.sh docker         # 等同 stack dev-up
```

**机制**（`compose.dev.yaml`）：

| 组件 | 热重载方式 |
|------|------------|
| **API** | 挂载 `./platform/app`、`./workers`；`uvicorn --reload` |
| **前端** | 挂载 `./platform-frontend`；容器内 **Vite dev**，保存 `.vue/.js` 即 HMR |
| **Worker** | 挂载 `./platform/app`；**改 Worker 逻辑后**需 `docker compose -p zhitan restart worker` |
| **文档** | 挂载 `./docs` 与《运维部署指南》；系统说明页刷新即见 |

访问方式：

| 服务 | 地址 |
|------|------|
| Web | `http://<服务器IP>:40005/ai/` |
| API | `http://<服务器IP>:18000`（KnowFlow iframe 同源） |
| 健康检查 | `http://127.0.0.1:18000/health` |

默认 API 端口绑定 **127.0.0.1:18000**（仅本机）。若需其他机器浏览器直连 API，在 `.env` 设 `STACK_DEV_API_PORT` 并调整 compose 绑定，或 SSH 隧道 `-L 18000:127.0.0.1:18000`。

### 3.2 开发迭代工作流

```bash
# 1. 拉代码
git pull

# 2. 若依赖变更
cd platform && .venv/bin/pip install -r requirements.txt   # 仅形态 C 需要
docker compose -p zhitan exec api pip install ...            # 一般 dev 镜像已含依赖

# 3. 已 dev-up 在跑则无需重启 API/前端；改 worker 任务时：
docker compose -p zhitan restart worker

# 4. 改 compose / .env 后
./dev.sh docker
```

**所见即所得范围**：

- 改 **Vue 组件 / 样式 / 路由** → 浏览器数秒内热更新。  
- 改 **FastAPI 路由 / 服务逻辑** → uvicorn 自动 reload，刷新页面即可。  
- 改 **Celery 任务** → restart worker 后生效。  
- 改 **platform/.env`** → restart api + worker。  
- 改 **根 .env / compose** → 重新 `dev-up`。

### 3.3 备选：服务器上 `local-dev`（venv）

适合不想跑 Docker 化 API、但依赖仍在同机 Docker 的场景：

```bash
# platform/.env 中 DATABASE_URL 等指向 127.0.0.1 映射端口或 host.docker.internal
./dev.sh local
```

需自行映射 postgres/redis 或使用 `EXPOSE_DEPS` 连本机 Docker 端口；**不如 dev-up 一体化**，仅作补充。

### 3.4 生产式 `stack up` 与热重载

`stack up` 使用 **Nginx 静态前端 + 无 reload 的 API**，**不支持**改源码即生效。  
若已用 `deploy.sh stack push` 部署镜像，要热重载需：

1. 在服务器保留 **git 仓库**，改用 `dev-up`；或  
2. 改代码后 `stack build api frontend && stack up`（慢，非所见即所得）。

**结论**：需要持续改代码的环境，请使用 **`dev-up`**，不要用生产 `up`。

---

## 4. 从镜像交付迁到单机源码 + 热重载

若当前是 `deploy.sh stack push` 仅镜像、无源码：

```bash
# 目标机
git clone <仓库> /opt/zhitan
cd /opt/zhitan
# 复制原 .env、platform/.env
bash scripts/stack.sh load images/zhitan-4.0.7-amd64.tar.gz   # 可选，加速首次 build
./dev.sh docker --profile knowflow --profile speech
```

数据卷 `data/` 若已在目标机，直接挂载；无需重复 restore。

---

## 5. 单机端口与安全建议

| 环境 | 建议暴露 | 不暴露 |
|------|----------|--------|
| 内网开发（dev-up） | 40005、18000（按需） | 5432、6379、9000、40007 |
| 生产（up） | **40005** | 其余全部 |

防火墙仅放行必要端口；`JWT_SECRET`、数据库密码、MinIO 密钥必须修改默认值。

---

## 6. 迁移检查清单

- [ ] `stack backup` 已完成且备份可解压  
- [ ] 目标机 `stack up` 或 `dev-up` 全容器 healthy  
- [ ] `platform/.env` 无 `REMOTE_DEPS=1`，地址为服务名或本机正确端口  
- [ ] `KNOWFLOW_UI_PUBLIC_URL` 与浏览器实际访问 origin 一致  
- [ ] 登录、上传、翻译、检索、对比冒烟通过  
- [ ] 开发态确认：改前端/API 文件后无需 rebuild 即可看到效果  
- [ ] Worker 任务改完后已 `restart worker`  
- [ ] 对外仅开放 40005（生产切 up 时）

---

## 7. 常见问题

| 现象 | 处理 |
|------|------|
| 迁移后 KnowFlow 502 | 等 MySQL/Infinity 就绪；`docker restart ragflow-server` |
| iframe 404 | 检查 `KNOWFLOW_UI_PUBLIC_URL` 是否与访问 URL 同源 |
| dev-up 改前端无反应 | 确认访问的是 :40005（Vite），不是旧 Nginx 缓存标签页 |
| API 改完不生效 | 看 `docker compose logs api` 是否 reload；是否改错未挂载目录 |
| Celery 任务行为旧 | `docker compose -p zhitan restart worker` |
| 仍连远程 40002 | 删除 `REMOTE_DEPS`，改 `DATABASE_URL` 为 `postgres:5432` |

---

## 相关文档

- [远程依赖开发（过渡方案）](server-deps.md)
- [部署指南](deployment.md)
- [数据库迁移](database-migration.md)
- [功能实现说明](feature-implementation.md)
- [根目录运维部署指南](../../../运维部署指南.md)
