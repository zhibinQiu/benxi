# 智碳平台 AI 文档

**当前版本 v3.9.3** · 运维与开发文档入口。

## 运维与部署

| 文档 | 说明 |
|------|------|
| [运维手册](operations/README.md) | **推荐**：部署、配置、迁移、热重载 |
| [组件位置与数据存储](operations/components-and-storage.md) | **各服务在哪、各库存什么、如何连接查看** |
| [配置文件与脚本](operations/config-and-scripts.md) | **Compose、.env、脚本、Mermaid** |
| [功能实现说明](operations/feature-implementation.md) | 各功能当前实现方式 |
| [单机迁移与热重载](operations/single-server-migration.md) | 迁到同一服务器 + dev-up |
| [运维部署指南（根目录）](../../运维部署指南.md) | 速查：架构图、端口、启停命令 |
| [系统架构](operations/architecture.md) | 分层与组件 |
| [部署指南](operations/deployment.md) | dev / 生产 / 镜像推送 |

## 开发

| 文档 | 说明 |
|------|------|
| [快速开始](getting-started.md) | 5 分钟上手 |
| [实现说明书总览](development/implementation-manual.md) | 开发导航 |
| [脚本说明](../../scripts/README.md) | `zhitan.sh` / `stack.sh` 职责 |

```bash
bash scripts/zhitan.sh dev              # 全 Docker 开发（推荐）
```
