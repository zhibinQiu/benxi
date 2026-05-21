# PDF 翻译与文档 AI 平台

基于 [BabelDOC](https://github.com/funstory-ai/BabelDOC) 的 PDF 科学文献翻译，以及企业文档管理 / 翻译控制面平台。

## 项目结构

```
pdf_trans/
├── pdf2zh_next/          # PDF 翻译核心（CLI、WebUI、REST API）
├── platform/             # 文档 AI 平台后端（FastAPI + Celery）
├── platform-frontend/    # 平台前端（Vue 3）
├── scripts/              # 启动与资源脚本
├── docs/zh/              # 中文文档
└── tests/                # pdf2zh 配置相关测试
```

## 快速启动（推荐）

```bash
# 1. 安装翻译核心
pip install -e .

# 2. 下载模型与字体（首次）
bash scripts/download_babeldoc_assets.sh

# 3. 安装平台后端
cd platform && python -m venv .venv && source .venv/bin/activate && pip install -e .

# 4. 安装平台前端
cd ../platform-frontend && npm install

# 5. 一键启动（本地优先：基础设施 Docker，应用进程在宿主机）
cd .. && bash scripts/start_platform.sh
```

| 服务 | 地址 |
|------|------|
| 平台前端 | http://127.0.0.1:5174 |
| 平台 API | http://127.0.0.1:8000/docs |
| pdf2zh API | http://127.0.0.1:7861 |
| 默认账号 | `admin` / `admin123` |

停止：`bash scripts/stop_platform.sh`

## 单独使用 PDF 翻译

```bash
pdf2zh_next document.pdf              # 命令行
pdf2zh_next --gui                     # Gradio WebUI :7860
pdf2zh_next --api --api-port 7861     # REST API
```

## 文档

- [快速开始](docs/zh/getting-started/getting-started.md)
- [本地开发](docs/zh/development/local-development.md)
- [文档平台](docs/zh/development/doc-platform.md)
- [REST API](docs/zh/development/rest-api.md)

## 许可

[AGPL v3](LICENSE)
