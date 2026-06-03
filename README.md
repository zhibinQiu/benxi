# PDF 翻译与智碳平台 AI 系统

基于 [BabelDOC](https://github.com/funstory-ai/BabelDOC) 的 PDF 科学文献翻译，以及智碳平台 AI 企业应用（文档、权限、知识库、双碳工具等）。

## 项目结构

```
pdf_trans/
├── compose.yaml              # 统一 Docker 栈（v3.4+）
├── compose.dev.yaml          # 开发：热重载、API :18000
├── deploy/knowflow.yml       # KnowFlow profile
├── platform/                 # FastAPI + Celery 后端
├── platform-frontend/        # Vue 3 前端
├── pdf2zh_next/              # PDF 翻译核心
├── scripts/stack.sh          # 编排入口
└── docs/zh/operations/       # 运维文档（最新）
```

## 快速启动

```bash
cp .env.stack.example .env
bash scripts/stack.sh dev-up --profile knowflow   # 按需加 speech
```

| 服务 | 地址 |
|------|------|
| Web | http://127.0.0.1:40005/ai/ |
| API（开发） | http://127.0.0.1:18000 |

停止：`bash scripts/stack.sh down`

## 文档（请勿被旧版误导）

| 文档 | 说明 |
|------|------|
| **[运维手册](docs/zh/operations/README.md)** | 架构、容器、网络、部署、配置、升级、安全 — **操作以此为准** |
| [快速开始](docs/zh/getting-started.md) | 5 分钟上手 |
| [开发实现说明书](docs/zh/development/implementation-manual.md) | 代码与模块 |
| [脚本说明](scripts/README.md) | stack / deploy |

预览全文：`pip install -r docs/requirements-docs.txt && mkdocs serve`

## 服务器部署

```bash
bash scripts/stack.sh build && bash scripts/stack.sh save
bash scripts/deploy.sh stack push
```

详见 [部署指南](docs/zh/operations/deployment.md)。

## 许可

[AGPL v3](LICENSE)
