# 平台架构与运维（索引）

> **本文已合并至运维专题文档**，请勿在此维护重复内容。  
> 操作命令以 `bash scripts/zhitan.sh --help` 与 [脚本说明](../../scripts/README.md) 为准。

## 推荐阅读

| 主题 | 文档 |
|------|------|
| 逻辑分层与组件 | [系统架构](../operations/architecture.md) |
| 端口、Nginx、iframe | [网络拓扑](../operations/network-topology.md) |
| 容器与镜像 | [Docker 容器说明](../operations/docker-services.md) |
| 环境变量 | [配置说明](../operations/configuration.md) |
| 启动与部署 | [部署指南](../operations/deployment.md) · [根目录运维部署指南](../../../运维部署指南.md) |
| 远程依赖开发 | [server-deps](../operations/server-deps.md) · `zhitan.sh remote-dev` → `local-dev` |

## 一分钟速查

| 场景 | 命令 |
|------|------|
| 全 Docker 开发 | `bash scripts/zhitan.sh dev` |
| 远程依赖 + 本机 venv | `bash scripts/zhitan.sh remote-dev` → `local-dev` |
| 生产式本机 | `bash scripts/stack.sh build && bash scripts/stack.sh up --profile knowflow` |
| 服务器交付 | `bash scripts/stack.sh save` → `bash scripts/deploy.sh stack push` |
| 停止 | `bash scripts/zhitan.sh stop` |

| 入口 | 地址 |
|------|------|
| Web | http://127.0.0.1:40005/ai/ |
| API（Docker dev） | http://127.0.0.1:18000 |
| API（本机 venv remote-dev） | http://127.0.0.1:8000 |

配置模板：`platform/.env.example`、根目录 `.env.stack.example`。

API 统一响应：`{ "code": 0, "message": "ok", "data": ... }`；业务错误 HTTP 4xx/5xx + `detail` 或 `message`。详见 [API 约定](../implementation/api-conventions.md)。
