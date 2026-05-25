# 智碳 AI平台（后端）

FastAPI 控制面：用户 / 部门 / 角色 / 文档 ACL / 异步任务 / 站内通知 / 审计。  
AI 能力通过 `app/features` 插件注册；PDF 翻译对接宿主机或容器内的 `pdf2zh_next --api`。

## 启动

推荐使用仓库根目录脚本（本地优先）：

```bash
bash scripts/start_platform.sh
```

详见 [智碳 AI平台说明](../docs/zh/development/doc-platform.md) 与 [功能插件](../docs/zh/platform/feature-plugins.md)。

## 技术栈

- FastAPI、PostgreSQL、MinIO、Redis、Celery

## 目录

```
platform/
  app/                 # FastAPI 应用与功能插件
  workers/             # Celery 任务
  docker-compose.yml   # 全栈 / 基础设施
  docker-compose.local.yml
```
