# 网关 + 端口规划（40000–40010）

## 原则

- **HTTP 可反代的**：统一走 **gateway :40005**（`/deps/…` 路径）
- **TCP 不可反代**：仍直连（postgres / redis / minio / mysql）
- **frp**：控制 **40007**，本机 dev 对外 **40008**（两端口分离，避免 port unavailable）

## 端口表

| 端口 | 用途 |
|------|------|
| 40000 | searxng（同机其它服务） |
| 40001 | Dify 设计系统 |
| 40002 | PostgreSQL（TCP） |
| 40003 | Redis（TCP） |
| 40004 | MinIO（TCP） |
| **40005** | **gateway nginx**（pdf2zh / speech / **RAGFlow API** / knowflow-backend / frontend） |
| 40006 | RAGFlow MySQL（TCP，原 40009 挪至此） |
| **40007** | **frps 控制**（frpc 连接） |
| **40008** | **frpc remote**（他人访问本机 Vite） |
| 40009 | 预留 |
| 40010 | 预留 |

## 服务器启用

```bash
cp .env.server.deps.example .env
GATEWAY_MODE=1 EXPOSE_DEPS=1 bash scripts/stack.sh up --profile knowflow --profile speech \
  gateway postgres redis minio pdf2zh-api speech-api \
  knowflow-mysql knowflow-infinity knowflow-gotenberg ragflow knowflow-backend
```

## 本机 remote-dev

```bash
REMOTE_HOST=172.19.134.45 ./dev.sh remote-dev
bash scripts/verify-remote-deps.sh
```

HTTP 依赖 URL 形如 `http://<IP>:40005/deps/pdf2zh`（见 `platform/.env.remote.example`）。RAGFlow 仅暴露 API（`/deps/ragflow/v1/…`），不部署 KnowFlow Web UI。

## 本机 dev 给他人看

```bash
./dev.sh local
frpc -c frpc.toml   # serverPort=40007, remotePort=40008
```

访问：**http://172.19.134.45:40008/ai/**

## 服务器启用（必须先做，才能释放 40007/40008 给 frp）

当前服务器若仍用旧 compose（40005–40009 各服务独立映射），frp 会报 **port unavailable**。
需先切到网关模式，HTTP 只留 **40005**，再改 frps 到 **40007**。

```bash
cp .env.server.deps.example .env
GATEWAY_MODE=1 EXPOSE_DEPS=1 bash scripts/stack.sh up --profile knowflow --profile speech \
  gateway postgres redis minio pdf2zh-api speech-api \
  knowflow-mysql knowflow-infinity knowflow-gotenberg ragflow knowflow-backend
```

完成后在服务器改 frps 并重启：

```bash
# /opt/frp/frps.toml → bindPort = 40007
systemctl restart frps
```

## 本机 frpc（网关迁移后）

```toml
serverPort = 40007
remotePort = 40008
```

访问：**http://172.19.134.45:40008/ai/**

## 迁移前临时方案

网关未切完前，frps 可先绑 **40010**（仅控制连接），`remotePort` 需等 **40008** 释放后再开。
