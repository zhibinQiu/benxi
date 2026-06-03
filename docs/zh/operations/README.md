# 运维与部署手册（v3.4+）

本目录为 **当前唯一推荐** 的部署与运维文档，基于根目录统一容器栈（`compose.yaml` + `scripts/stack.sh`）。

!!! warning "旧文档说明"
    `development/deploy-amd64.md`、`development/v3.4-baseline.md`、`development/docker-unified-deployment-proposal.md` 等保留作历史参考，**操作请以本目录为准**。  
    已废弃：`platform/docker-compose*.yml` 宿主机混合模式、`merge-stack-env.sh`。

## 文档索引

| 文档 | 内容 |
|------|------|
| [系统架构](architecture.md) | 分层、开源组件、数据流、与同类产品对比 |
| [Docker 容器说明](docker-services.md) | 每个容器的职责、镜像、端口、依赖 |
| [网络与反代拓扑](network-topology.md) | 40005/18000、Nginx、KnowFlow iframe 转发 |
| [部署指南](deployment.md) | 本地 dev、生产 up、amd64/arm64 镜像推送 |
| [配置说明](configuration.md) | `.env`、`.env.stack.example`、`platform/.env` |
| [数据库迁移](database-migration.md) | schema_migrate、升级注意 |
| [权限与账户](permissions.md) | RBAC、文档分级、KnowFlow 账号映射 |
| [测试](testing.md) | 平台测试、冒烟清单 |
| [升级](upgrade.md) | 版本 bump、镜像 save/load、回滚 |
| [安全](security.md) | 暴露面、密钥、JWT、生产 checklist |
| [日常操作手册](operations-manual.md) | 启停、日志、备份、故障排查 |

## 一分钟速查

```bash
# 开发（热重载 + KnowFlow + 语音）
cp .env.stack.example .env    # 首次；密钥见 platform/.env.example
bash scripts/stack.sh dev-up --profile knowflow --profile speech

# 生产式本机
bash scripts/stack.sh build --profile knowflow
bash scripts/stack.sh up --profile knowflow

# 远程 amd64（仅镜像，不 rsync 源码）
bash scripts/stack.sh build && bash scripts/stack.sh save
bash scripts/deploy.sh stack push
```

| 入口 | 地址 |
|------|------|
| Web | http://127.0.0.1:40005/ai/ |
| API（开发直连） | http://127.0.0.1:18000 |
| 健康检查 | http://127.0.0.1:18000/health |

本地预览文档站：

```bash
pip install -r docs/requirements-docs.txt
mkdocs serve -a 127.0.0.1:8765
# 浏览器打开 http://127.0.0.1:8765
```

默认管理员见 `platform/.env.example` 中 `BOOTSTRAP_ADMIN_*`（开发常用手机号登录）。
