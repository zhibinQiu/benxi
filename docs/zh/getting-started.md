# 快速开始

智碳平台 AI 系统 v3.4+ 使用 **统一 Docker 栈**。完整说明见 [运维手册](operations/README.md)。

## 1. 环境

- Docker 24+、Docker Compose v2
- 可选：8GB+ 内存（KnowFlow / 语音）

## 2. 配置

```bash
cp .env.stack.example .env
# 从 platform/.env.example 复制 JWT_SECRET、BOOTSTRAP_ADMIN_* 等到 .env
```

启用知识库与语音（可选）：

```bash
# .env
KNOWFLOW_ENABLED=true
STACK_PROFILES="knowflow speech"
```

## 3. 启动

**开发（推荐，支持热重载）：**

```bash
bash scripts/stack.sh dev-up --profile knowflow --profile speech
```

**生产式本机：**

```bash
bash scripts/stack.sh build --profile knowflow
bash scripts/stack.sh up --profile knowflow
```

等价入口：`bash scripts/zhitan.sh`（默认 stack up）、`bash scripts/zhitan.sh dev`（dev-up）。

## 4. 访问

| 服务 | 地址 |
|------|------|
| Web | http://127.0.0.1:40005/ai/ |
| API（开发） | http://127.0.0.1:18000 |
| API 文档 | http://127.0.0.1:18000/docs |

默认管理员见 `.env` 中 `BOOTSTRAP_ADMIN_PHONE` / `BOOTSTRAP_ADMIN_PASSWORD`（模板在 `platform/.env.example`）。

## 5. 停止

```bash
bash scripts/stack.sh down
```

## 6. 服务器部署

```bash
bash scripts/stack.sh build && bash scripts/stack.sh save
bash scripts/deploy.sh stack push   # 需 platform/deploy.target
```

详见 [部署指南](operations/deployment.md)。

## 仅使用 PDF 翻译

```bash
pip install -e .
bash scripts/download_babeldoc_assets.sh
pdf2zh_next document.pdf
```

更多：[REST API](development/rest-api.md)
