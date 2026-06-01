# REST API 开发文档（Vue / 外部前端）

本文档描述 `pdf2zh_next --api` 提供的 **REST + SSE** 接口。智碳平台AI系统经 `platform` 代理调用；也可用于自建客户端。

> [!NOTE]
> pdf2zh 1.x 的 Flask/Celery/Redis HTTP API 已移除；仅以本文档（`pdf2zh_next --api`）为准。

---

## 目录

- [启动与配置](#启动与配置)
- [通用约定](#通用约定)
- [接口一览](#接口一览)
- [GET /api/health](#get-apihealth)
- [GET /api/meta](#get-apimeta)
- [POST /api/jobs](#post-apijobs)
- [GET /api/jobs/{job_id}](#get-apijobsjob_id)
- [GET /api/jobs/{job_id}/events](#get-apijobsjob_idevents)
- [GET /api/jobs/{job_id}/download/{kind}](#get-apijobsjob_iddownloadkind)
- [DELETE /api/jobs/{job_id}](#delete-apijobsjob_id)
- [SSE 事件类型](#sse-事件类型)
- [术语表（词汇库）](#术语表词汇库)
- [与 Vue 前端联调](#与-vue-前端联调)
- [OpenAPI](#openapi)

---

## 启动与配置

### 启动 API 服务

```bash
cd /path/to/pdf_trans
.venv/bin/pdf2zh_next --api
```

| 项 | 默认值 | 说明 |
|----|--------|------|
| 监听地址 | `127.0.0.1` | 代码内 `run_api_server(host=...)` |
| 端口 | `7861` | CLI：`--api-port`（配置项 `gui_settings.api_port`） |
| 实现 | FastAPI + uvicorn | 源码：`pdf2zh_next/api_server.py` |

启动前会执行 BabelDOC 资源 **warmup**（与 CLI 一致）。

### 翻译引擎与密钥

API **不单独管理** API Key。引擎凭证、默认语言等仍来自：

- `~/.config/pdf2zh/config.v3.toml`
- 环境变量（`PDF2ZH_*`，规则见 [进阶文档](../advanced/advanced.md)）
- CLI 参数（若与 `--api` 同进程传入）

可用环境变量 `PDF2ZH_GUI_SETTINGS_ENABLED_SERVICES` 限制 `/api/meta` 返回的引擎列表（逗号分隔，与 Gradio 相同）。

### 与 Gradio 并存

| 服务 | 命令 | 默认端口 |
|------|------|----------|
| Gradio WebUI | `pdf2zh_next --gui` | 7860 |
| REST API | `pdf2zh_next --api` | 7861 |
| 平台前端 | `cd platform-frontend && npm run dev` | 40005（平台 API 代理翻译） |

---

## 通用约定

| 项 | 说明 |
|----|------|
| Base URL | `http://127.0.0.1:7861`（生产环境替换为实际主机） |
| Content-Type | JSON 接口：`application/json`；创建任务：`multipart/form-data` |
| CORS | 允许 `*`（开发用）；生产建议收紧 `allow_origins` |
| 鉴权 | 当前 **无** 内置 Token；勿将 API 直接暴露公网 |
| 任务存储 | 内存字典 `_jobs`，进程重启后任务丢失 |

---

## 接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/meta` | 语言、引擎、术语表格式 |
| `POST` | `/api/jobs` | 创建翻译任务（上传 PDF + 可选术语表） |
| `GET` | `/api/jobs/{job_id}` | 查询任务状态与结果路径 |
| `GET` | `/api/jobs/{job_id}/events` | **SSE** 实时进度与完成事件 |
| `GET` | `/api/jobs/{job_id}/download/{kind}` | 下载 PDF / 术语表 / **提取文本**（见下表） |
| `DELETE` | `/api/jobs/{job_id}` | 取消进行中的任务 |

---

## GET /api/health

**响应示例：**

```json
{ "ok": true }
```

---

## GET /api/meta

获取前端初始化所需元数据。

**响应示例：**

```json
{
  "languages": [
    { "code": "en", "label": "English" },
    { "code": "zh-CN", "label": "Simplified Chinese" }
  ],
  "engines": [
    { "id": "siliconflowfree", "supports_glossary": true },
    { "id": "bing", "supports_glossary": false }
  ],
  "glossary_format": {
    "columns": ["source", "target", "tgt_lng"],
    "example": "source,target,tgt_lng\nAutoML,自动 ML,zh-CN"
  }
}
```

| 字段 | 说明 |
|------|------|
| `engines[].id` | 与 CLI 引擎标志一致（如 `--openai` 对应 `openai`） |
| `engines[].supports_glossary` | 是否支持自定义术语表（即 BabelDOC `support_llm`） |

---

## POST /api/jobs

创建异步翻译任务。

### 请求（multipart/form-data）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | 文件 | 是 | PDF，扩展名须为 `.pdf` |
| `lang_in` | 字符串 | 否 | 源语言，默认 `en` |
| `lang_out` | 字符串 | 否 | 目标语言，默认 `zh-CN` |
| `service` | 字符串 | 是 | 翻译引擎 id，须为 `/api/meta` 中之一 |
| `glossary_files` | 文件（可多个） | 否 | UTF-8 CSV 术语表；仅 `supports_glossary: true` 的引擎 |

### 成功响应 `200`

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending"
}
```

### 错误

| HTTP | 原因 |
|------|------|
| `400` | 非 PDF、未知 `service`、引擎不支持术语表却上传了 `glossary_files`、配置校验失败 |
| `500` | 无可用翻译引擎（配置问题） |

### cURL 示例

```bash
curl -X POST http://127.0.0.1:7861/api/jobs \
  -F "file=@paper.pdf" \
  -F "lang_in=en" \
  -F "lang_out=zh-CN" \
  -F "service=siliconflowfree" \
  -F "glossary_files=@my-glossary.csv"
```

多术语表：

```bash
curl -X POST http://127.0.0.1:7861/api/jobs \
  -F "file=@paper.pdf" \
  -F "service=openai" \
  -F "glossary_files=@g1.csv" \
  -F "glossary_files=@g2.csv"
```

服务端将多个 CSV 写入临时文件，并以逗号拼接路径写入 `translation.glossaries`（与 CLI `--glossaries` 一致）。

---

## GET /api/jobs/{job_id}

查询任务快照（不订阅 SSE 时轮询用）。

**响应示例：**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "error": null,
  "progress": {
    "stage": "翻译段落",
    "overall_progress": 42.5,
    "part_index": 0,
    "total_parts": 1,
    "stage_current": 10,
    "stage_total": 24
  },
  "files": {
    "mono": "/tmp/.../output/paper-mono.pdf",
    "dual": "/tmp/.../output/paper-dual.pdf",
    "glossary": null,
    "extracted_json": "/tmp/.../paper-extracted.json",
    "extracted_md": "/tmp/.../paper-extracted.md"
  },
  "token_usage": null
}
```

### `status` 枚举

| 值 | 说明 |
|----|------|
| `pending` | 已创建，尚未运行 |
| `running` | 翻译中 |
| `done` | 成功完成 |
| `error` | 失败，`error` 字段有说明 |
| `cancelled` | 已取消 |

---

## GET /api/jobs/{job_id}/events

**Server-Sent Events** 流，与 WebUI 内部 `do_translate_async_stream` 事件格式对齐。

### 请求

```http
GET /api/jobs/{job_id}/events
Accept: text/event-stream
```

### SSE 帧格式

每条消息包含：

- `event`: 事件类型名（见下表）
- `data`: JSON 字符串

连接建立后先推送 `snapshot`（当前状态），任务已结束则再推送 `complete` 并关闭；进行中则持续推送直至 `complete`。

### 客户端示例（浏览器）

```javascript
const es = new EventSource(`/api/jobs/${jobId}/events`);

es.addEventListener("progress_update", (e) => {
  const data = JSON.parse(e.data);
  console.log(data.stage, data.overall_progress);
});

es.addEventListener("finish", (e) => {
  const data = JSON.parse(e.data);
  console.log(data.translate_result);
});

es.addEventListener("complete", (e) => {
  const data = JSON.parse(e.data);
  console.log("done", data.status, data.files);
  es.close();
});
```

调用方可自行封装 SSE 订阅（参考 `platform-frontend/src/api/client.js` 中的任务轮询模式）。

---

## GET /api/jobs/{job_id}/download/{kind}

下载结果文件。

| `kind` | 文件 |
|--------|------|
| `mono` | 单语译文 PDF |
| `dual` | 双语对照 PDF |
| `glossary` | 自动提取的术语表（若任务开启并成功生成） |
| `extracted-json` | 提取/译文段落文本（JSON，按页与段落组织） |
| `extracted-md` | 提取/译文段落文本（Markdown） |

任务完成后由 `write_extracted_exports` 生成：优先使用 `il_translated.json`（仅当 `debug=True` 时由 BabelDOC 写入）；API 默认 `debug=False` 以避免 PDF 上出现调试框，此时从译文 PDF 提取文本。

**响应：** `FileResponse`，`Content-Disposition` 带原始文件名。

**错误 `404`：** 任务不存在、该类型文件未生成或磁盘文件已删除。

```bash
curl -OJ "http://127.0.0.1:7861/api/jobs/{job_id}/download/mono"
```

---

## DELETE /api/jobs/{job_id}

取消进行中的后台任务。

**响应示例：**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "cancelled"
}
```

若任务已完成或不存在，行为见实现：不存在返回 `404`；已完成则状态可能已为 `done`（取消无效）。

---

## SSE 事件类型

与 BabelDOC / `do_translate_async_stream` 一致的主要类型：

| `event` | 说明 |
|---------|------|
| `snapshot` | 连接时当前 `status` / `progress` / `files` |
| `job_started` | 任务开始执行 |
| `stage_summary` | 各阶段权重（可选） |
| `progress_start` | 某阶段开始 |
| `progress_update` | 进度更新（含 `overall_progress`、`stage` 等） |
| `progress_end` | 某阶段结束 |
| `finish` | 翻译完成，含 `translate_result` |
| `error` | 错误，`error` 字段为说明 |
| `job_finished` | 后台任务结束 |
| `cancelled` | 已取消 |
| `complete` | **终端事件**，payload 为任务快照（`status`、`files`、`error`） |

### `finish` 事件中 `translate_result` 字段（序列化后）

```json
{
  "mono_pdf_path": "/path/to/mono.pdf",
  "dual_pdf_path": "/path/to/dual.pdf",
  "auto_extracted_glossary_path": "/path/to/glossary.csv",
  "original_pdf_path": "/path/to/input.pdf"
}
```

---

## 术语表（词汇库）

### CSV 格式

| 列 | 含义 |
|----|------|
| `source` | 原文 |
| `target` | 译文 |
| `tgt_lng` | 目标语言代码，须与 `lang_out` 一致 |

```csv
source,target,tgt_lng
AutoML,自动 ML,zh-CN
machine learning,机器学习,zh-CN
```

### API 行为

1. 仅当 `service` 对应引擎 `supports_glossary === true` 时接受 `glossary_files`。
2. 服务端检测编码（`chardet`），统一以 UTF-8 写入临时 CSV。
3. 多个文件路径以 **英文逗号** 拼接传入 `SettingsModel.translation.glossaries`。

自动术语提取、保存自动术语表等 **未在 REST MVP 中暴露** 表单项；行为跟随 `~/.config/pdf2zh` 默认配置。详见 [进阶文档 · 术语表支持](../advanced/advanced.md)。

---

## 与 Vue 前端联调

| 文件 | 作用 |
|------|------|
| `platform/.env` | `PDF2ZH_API_URL` 指向本机 `:7861` |
| `platform-frontend/vite.config.js` | 平台 `/api` 代理到 `:8000` |
| `VITE_API_BASE` | 生产构建时 API 根地址（默认可为空，走同源或反向代理） |

开发流程见 [本地开发指南 · Vue 前端](./local-development.md#42-vue-前端与-gradio-并存)。

---

## OpenAPI

服务启动后访问：

- Swagger UI：<http://127.0.0.1:7861/docs>
- ReDoc：<http://127.0.0.1:7861/redoc>
- OpenAPI JSON：<http://127.0.0.1:7861/openapi.json>

由 FastAPI 根据 `api_server.py` 自动生成，与本文档不一致时 **以代码为准**。

---

## 实现参考

| 模块 | 路径 |
|------|------|
| 路由与任务 | `pdf2zh_next/api_server.py` |
| CLI 入口 | `pdf2zh_next/main.py`（`--api` 同步启动 uvicorn） |
| 翻译流 | `pdf2zh_next/high_level.py` → `do_translate_async_stream` |
| 配置模型 | `pdf2zh_next/config/model.py`（`basic.api`、`gui_settings.api_port`） |

---

<div align="right">
<h6><small>本文档随 REST API 实现更新；提交 API 变更时请同步修改本节。</small></h6>
</div>
