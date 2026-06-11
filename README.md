# PDF 翻译与智碳平台 AI 系统

基于 [BabelDOC](https://github.com/funstory-ai/BabelDOC) 的 PDF 科学文献翻译，以及智碳平台 AI 企业应用（文档、权限、知识库、双碳工具等）。

**当前版本：v4.0.0**（见根目录 `VERSION`）

## 项目结构

```
pdf_trans/
├── VERSION                   # 单一版本源（4.0.0）
├── compose.yaml              # 统一 Docker 栈
├── compose.dev.yaml          # 开发：热重载、API :18000
├── deploy/knowflow.yml       # KnowFlow profile
├── platform/                 # FastAPI + Celery 后端
├── platform-frontend/        # Vue 3 前端
├── pdf2zh_next/              # PDF 翻译核心
├── scripts/
│   ├── zhitan.sh             # 开发入口（推荐）
│   └── stack.sh              # 容器编排
└── docs/zh/operations/       # 运维与架构文档
```

## 快速启动

```bash
cp .env.stack.example .env
cp platform/.env.example platform/.env    # 按需编辑

bash scripts/zhitan.sh dev --profile knowflow
# 可选: --profile speech
```

| 服务 | 地址 |
|------|------|
| Web | http://127.0.0.1:40005/ai/ |
| API（开发直连） | http://127.0.0.1:18000 |

停止：`bash scripts/zhitan.sh stop`

## 文档

| 文档 | 说明 |
|------|------|
| **[运维部署指南](运维部署指南.md)** | **启动 / 部署 / 迁移**、架构图、网络图、端口与组件 — **根目录速查** |
| [运维手册](docs/zh/operations/README.md) | 部署、配置、升级、安全 — **操作以此为准** |
| [系统架构](docs/zh/operations/architecture.md) | 分层、组件、KnowFlow 集成 |
| [快速开始](docs/zh/getting-started.md) | 5 分钟上手 |
| [脚本说明](scripts/README.md) | zhitan / stack / deploy |

预览文档站：`pip install -r docs/requirements-docs.txt && mkdocs serve`

## 远程依赖开发

本机跑前端 + API，数据库/KnowFlow 在远程服务器：

```bash
REMOTE_HOST=你的服务器IP bash scripts/zhitan.sh remote-dev
bash scripts/verify-remote-deps.sh
bash scripts/zhitan.sh local-dev      # 推荐：本机 venv + Vite
bash scripts/zhitan.sh local-status
```

全 Docker 开发栈（API :18000）：`bash scripts/zhitan.sh dev`

## 服务器部署

```bash
bash scripts/stack.sh build && bash scripts/stack.sh save
bash scripts/deploy.sh stack push
```

详见 [部署指南](docs/zh/operations/deployment.md)。

## 许可

[AGPL v3](LICENSE)
