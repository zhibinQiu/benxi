# 绿叶 AI 办公系统

基于 [BabelDOC](https://github.com/funstory-ai/BabelDOC) 的 PDF 科学文献翻译，以及企业 AI 办公应用（文档、权限、知识库、智能工具等）。

**当前版本：v4.0.1**（见根目录 `VERSION`）

## 项目结构

```
pdf_trans/
├── VERSION                   # 单一版本源
├── dev.sh                    # 开发与运维统一入口（推荐）
├── compose.yaml              # 统一 Docker 栈
├── compose.dev.yaml          # 开发：热重载、API :18000
├── platform/                 # FastAPI + Celery 后端
├── platform-frontend/        # Vue 3 前端
├── pdf2zh_next/              # PDF 翻译核心
└── scripts/
    ├── dev.sh                # 同上（主实现）
    └── stack.sh              # 容器编排
```

## 快速启动

```bash
cp .env.stack.example .env
cp platform/.env.example platform/.env    # 按需编辑

# 全 Docker 开发
./dev.sh docker --profile knowflow

# 或：本机 venv + 远程依赖（见下方）
```

| 模式 | Web | API |
|------|-----|-----|
| 本机 dev | http://127.0.0.1:40005/ai/ | http://127.0.0.1:8000 |
| Docker dev | http://127.0.0.1:40005/ai/ | http://127.0.0.1:18000 |

停止：`./dev.sh stop`

## 远程依赖开发

本机跑前端 + API，数据库/KnowFlow 在远程服务器：

```bash
REMOTE_HOST=你的服务器IP ./dev.sh remote-dev
bash scripts/verify-remote-deps.sh
./dev.sh local
```

## 文档

| 文档 | 说明 |
|------|------|
| **[运维部署指南](运维部署指南.md)** | 启动 / 部署 / 迁移 |
| [运维手册](docs/zh/operations/README.md) | 部署、配置、升级 |
| [脚本说明](scripts/README.md) | dev / stack / deploy |

## 服务器部署

```bash
./dev.sh stack build && ./dev.sh stack save
./dev.sh deploy stack push
```

详见 [部署指南](docs/zh/operations/deployment.md)。

## 许可

[AGPL v3](LICENSE)
