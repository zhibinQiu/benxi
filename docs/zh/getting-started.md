# 快速开始

智碳平台 AI 系统 v3.9.3 使用 **统一 Docker 栈**。完整说明见 [运维手册](operations/README.md) 与 [根目录运维部署指南](../../运维部署指南.md)。

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

**开发（热重载，推荐）：**

```bash
bash scripts/zhitan.sh dev
# 等价：bash scripts/stack.sh dev-up --profile knowflow --profile speech
```

**生产式本机：**

```bash
bash scripts/stack.sh build --profile knowflow
bash scripts/stack.sh up --profile knowflow
```

## 4. 访问

| 服务 | 地址 |
|------|------|
| Web | http://127.0.0.1:40005/ai/ |
| API（开发） | http://127.0.0.1:18000 |

组件与数据库说明见 [组件位置与数据存储](operations/components-and-storage.md)。

默认管理员见 `.env` 中 `BOOTSTRAP_ADMIN_PHONE` / `BOOTSTRAP_ADMIN_PASSWORD`（模板在 `platform/.env.example`）。

## 5. 停止

```bash
bash scripts/zhitan.sh stop
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
