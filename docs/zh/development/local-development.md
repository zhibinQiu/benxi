# 本地开发指南

面向在本机开发与调试 `pdf_trans` 仓库的贡献者。

## 1. 项目结构

| 路径 | 说明 |
|------|------|
| `pdf2zh_next/` | PDF 翻译核心（CLI、Gradio、REST API） |
| `platform/` | 智碳 AI平台后端 |
| `platform-frontend/` | 平台 Vue 前端 |
| `scripts/` | `start_platform.sh`、`stop_platform.sh`、`download_babeldoc_assets.sh` |
| `assets/babeldoc/` | BabelDOC 模型/字体（可选，见下文） |
| `.venv/` | 根目录虚拟环境（翻译核心） |
| `platform/.venv/` | 平台后端虚拟环境 |

在 Cursor / VS Code 中请打开 **仓库根目录** `pdf_trans`。

## 2. 环境准备

```bash
cd /path/to/pdf_trans

# 翻译核心
pip install -e .

# 平台后端
cd platform && python -m venv .venv && source .venv/bin/activate && pip install -e .

# 平台前端
cd ../platform-frontend && npm install
```

## 3. BabelDOC 资源

```bash
bash scripts/download_babeldoc_assets.sh
# 或
.venv/bin/pdf2zh_next --warmup
```

默认缓存：`~/.cache/babeldoc/`。可将 `assets/babeldoc/` 软链到该路径（脚本会自动处理）。

## 4. 运行方式

### 4.1 智碳 AI平台（推荐）

```bash
bash scripts/start_platform.sh
```

### 4.2 仅 PDF 翻译

```bash
.venv/bin/pdf2zh_next --gui                    # WebUI :7860
.venv/bin/pdf2zh_next --api --api-port 7861    # REST API
.venv/bin/pdf2zh_next document.pdf -o ./out    # 命令行
```

REST API 说明见 [rest-api.md](rest-api.md)。平台通过 `PDF2ZH_API_URL` 代理翻译任务。

## 5. 故障排查

### 解释器被 Homebrew 覆盖

工作区 `.vscode/settings.json` 建议设置 `python.useEnvironmentsExtension: false`，并指定 `.venv/bin/python`。

### `~/.cache/babeldoc` 软链嵌套

若曾在已存在的目录上 `ln -sfn`，可能产生 `babeldoc/babeldoc/` 嵌套。用 `rsync` 合并到 `assets/babeldoc/` 后删除原目录再重建软链。

### warmup 重复下载

确认模型文件路径为 `~/.cache/babeldoc/models/<文件名>.onnx` 且 SHA3-256 校验通过。

## 6. 路径速查

| 项 | 路径 |
|----|------|
| 资源脚本 | `scripts/download_babeldoc_assets.sh` |
| 平台启动 | `scripts/start_platform.sh` |
| 用户配置 | `~/.config/pdf2zh/config.v3.toml` |
| Debug 中间 JSON | `~/.cache/babeldoc/working/<pdf_stem>/` |
| 平台文档 | [doc-platform.md](doc-platform.md) |
