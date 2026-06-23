# 运维与部署手册（v4.2.1）

本目录为 **当前唯一推荐** 的部署与运维文档，基于根目录统一容器栈（`compose.yaml` + `scripts/stack.sh`）。

!!! warning "旧文档说明"
    历史文档 `deploy-amd64.md`、`local-development.md`、`doc-platform.md` 等已删除或合并，**操作请以本目录与根目录 [运维部署指南](../../运维部署指南.md) 为准**。  
    已废弃：`platform/docker-compose*.yml` 宿主机混合模式、`merge-stack-env.sh`。

## 文档索引

| 文档 | 内容 |
|------|------|
| [**运维部署指南（根目录）**](../../运维部署指南.md) | 启动 / 部署 / 迁移、架构图、端口速查 |
| [**组件位置与数据存储**](components-and-storage.md) | **各服务在哪、各库存什么、如何连接查看** |
| [**知识库数据一致性**](knowledge-data-consistency.md) | **存在即复用、孤儿清理、分层与权限、对账脚本** |
| [**配置文件与脚本**](config-and-scripts.md) | **Compose 文件、.env、脚本职责、Mermaid 说明** |
| [系统架构](architecture.md) | 分层、开源组件、数据流 |
| [Docker 容器说明](docker-services.md) | 每个容器的职责、镜像、端口、依赖 |
| [网络与反代拓扑](network-topology.md) | 40005/18000、Nginx、KnowFlow iframe |
| [部署指南](deployment.md) | 本地 dev、生产 up、amd64/arm64 镜像推送 |
| [远程依赖开发](server-deps.md) | 过渡：本机 API + 远程 40002–40009 |
| [**单机迁移与热重载**](single-server-migration.md) | **迁到同一台服务器 + 部署后 dev-up 热重载** |
| [**功能实现说明**](feature-implementation.md) | **当前各功能实现方式（无代码）** |
| [配置说明](configuration.md) | `.env`、`.env.stack.example`、`platform/.env` |
| [数据库迁移](database-migration.md) | schema_migrate、升级注意 |
| [权限与账户](permissions.md) | RBAC、文档分级、KnowFlow 账号映射 |
| [测试](testing.md) | 平台测试、冒烟清单 |
| [升级](upgrade.md) | 版本 bump、镜像 save/load、回滚 |
| [安全](security.md) | 暴露面、密钥、JWT、生产 checklist |
| [日常操作手册](operations-manual.md) | 启停、日志、备份、故障排查 |

## 一分钟速查

```bash
# 全 Docker 开发（本机或服务器，热重载）
./dev.sh docker

# 远程依赖 + 本机 venv（过渡，目标改为单机 dev）
# REMOTE_HOST=服务器IP ./dev.sh remote-dev && ./dev.sh local
# 见 single-server-migration.md

# 生产式本机
bash scripts/stack.sh build --profile knowflow
bash scripts/stack.sh up --profile knowflow

# 远程 amd64（仅镜像）
bash scripts/stack.sh build && bash scripts/stack.sh save
bash scripts/deploy.sh stack push
```

| 入口 | 地址 |
|------|------|
| Web | http://127.0.0.1:40005/ai/ |
| API（Docker dev） | http://127.0.0.1:18000 |
| API（本机 venv） | http://127.0.0.1:8000 |

脚本职责见 [scripts/README.md](../../scripts/README.md)。

本地预览文档站：

```bash
pip install -r docs/requirements-docs.txt
mkdocs serve -a 127.0.0.1:8765
```

默认管理员：**账号 `admin`，密码 `admin123`**（见 `platform/.env.example` 中 `BOOTSTRAP_ADMIN_*`）。
