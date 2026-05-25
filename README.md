# PDF 翻译与智碳 AI平台

基于 [BabelDOC](https://github.com/funstory-ai/BabelDOC) 的 PDF 科学文献翻译，以及智碳 AI 企业应用控制面（文档、权限、翻译任务等）。

## 项目结构

```
pdf_trans/
├── pdf2zh_next/          # PDF 翻译核心（CLI、WebUI、REST API）
├── platform/             # 智碳 AI平台后端（FastAPI + Celery）
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

### 知识问答（KnowFlow）

平台 **系统功能 → 知识问答** 内嵌 KnowFlow / RAGFlow 自带界面（:9380）。Apple Silicon 需 **从源码构建** arm64 镜像：

```bash
bash scripts/setup_knowflow.sh
bash scripts/build_knowflow_source.sh   # 首次约 30–90 分钟
bash scripts/start_platform.sh knowflow
```

| 服务 | 地址 |
|------|------|
| RAGFlow UI | http://127.0.0.1:9380 |
| KnowFlow API | http://127.0.0.1:5001 |

### 录音转文字（本地 Docker）

系统功能 → **录音转文字**：**FunASR**（Paraformer + VAD + 标点）+ **CAM++** 说话人分离 + **DeepSeek** 在线总结。

```bash
bash scripts/setup_speech.sh          # 首次：构建 speech-api，模型下载到 .run/speech-models/
# platform/.env 设置 DEEPSEEK_API_KEY（或与 pdf2zh 共用 ~/.config/pdf2zh 配置）
bash scripts/start_platform.sh speech
```

| 服务 | 地址 |
|------|------|
| speech-api（FunASR 转写） | http://127.0.0.1:8765 |
| DeepSeek（总结） | 平台 API 直连 api.deepseek.com |

## 单独使用 PDF 翻译

```bash
pdf2zh_next document.pdf              # 命令行
pdf2zh_next --gui                     # Gradio WebUI :7860
pdf2zh_next --api --api-port 7861     # REST API
```

## 文档

- [快速开始](docs/zh/getting-started/getting-started.md)
- [本地开发](docs/zh/development/local-development.md)
- [智碳 AI平台](docs/zh/development/doc-platform.md)
- [REST API](docs/zh/development/rest-api.md)

## 许可

[AGPL v3](LICENSE)
