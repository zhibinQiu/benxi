# 快速开始

本仓库包含 **PDF 科学文献翻译**（`pdf2zh_next`）与 **智碳平台 AI 系统**（`platform` + `platform-frontend`）。按你的目标选择路径。

## 智碳平台（推荐）

一键本地开发环境（基础设施 Docker，应用在宿主机）：

```bash
pip install -e .
bash scripts/download_babeldoc_assets.sh
cd platform && python -m venv .venv && source .venv/bin/activate && pip install -e .
cd ../platform-frontend && npm install
cd .. && bash scripts/start_platform.sh
```

| 服务 | 地址 |
|------|------|
| 平台前端 | http://127.0.0.1:40005/ai/ |
| 平台 API | http://127.0.0.1:8000/docs |
| pdf2zh API | http://127.0.0.1:7861 |
| 默认账号 | `admin` / `admin123` |

停止：`bash scripts/stop_platform.sh`

延伸阅读：[智碳平台说明](development/doc-platform.md)、[本地开发](development/local-development.md)、[脚本索引](../../scripts/README.md)。

## 仅使用 PDF 翻译

### 安装

```bash
pip install -e .
bash scripts/download_babeldoc_assets.sh   # 或: pdf2zh_next --warmup
```

### 命令行

```bash
pdf2zh_next document.pdf
pdf2zh_next "path with spaces/document.pdf"
```

输出在**当前工作目录**。更多参数见 [进阶选项](advanced/advanced.md)。

### WebUI（Gradio）

```bash
pdf2zh_next --gui
```

浏览器打开 http://127.0.0.1:7860 。

### REST API

```bash
pdf2zh_next --api --api-port 7861
```

交互式文档：http://127.0.0.1:7861/docs 。详见 [REST API](development/rest-api.md)。

## 可选能力

| 能力 | 首次准备 | 启动 |
|------|----------|------|
| 知识问答（KnowFlow） | `bash scripts/setup_knowflow.sh` + `bash scripts/build_knowflow_source.sh` | `bash scripts/start_platform.sh knowflow` |
| 录音转文字 | `bash scripts/setup_speech.sh`，配置 `platform/.env` 中 `DEEPSEEK_API_KEY` | `bash scripts/start_platform.sh speech` |

## amd64 服务器部署

```bash
# 本机配置 platform/deploy.target.amd64 后
bash scripts/push_and_deploy.sh
```

或目标机直接：`bash scripts/deploy_amd64.sh full`。见 [amd64 部署](development/deploy-amd64.md)。

## 其他安装方式

Windows 安装包、独立 Docker 镜像等见上游 [PDFMathTranslate-next](https://github.com/PDFMathTranslate-next/PDFMathTranslate-next) 文档；本 monorepo 以源码 + `scripts/start_platform.sh` 为主。
