# 知识服务实现

> 说明书 · 第三篇 §3.5 · [开发实现说明书总览](../development/implementation-manual.md)

本文描述平台**原生知识能力**（非 KnowFlow 前端嵌入）的实现：文档同步、分块索引、PageIndex 结构索引、混合检索与问答。重点说明**模块边界**与**关键函数的实现思路**。

---

## 1. 能力总览

| 能力 | 入口 | 后端引擎 |
|------|------|----------|
| 文档上传后索引 | 后台 `document_index` Job | KnowFlow 向量分块（默认 naive） |
| 重新索引 | `POST /knowledge/documents/{id}/reindex` | PageIndex（默认）或 KnowFlow 分块 |
| 知识检索问答 | `KnowledgeSearchView` / 流式 API | PageIndex 树搜索 + KnowFlow 向量 + 本地 fallback |
| 切片浏览 | `GET /knowledge/documents/{id}/chunks` | KnowFlow API |
| 引用预览 | `GET /knowledge/citations/preview` | PDF 页截图 / bbox 高亮 |

```mermaid
flowchart TB
  subgraph facade [域 Facade]
    KG[knowledge / KnowledgeGateway]
  end

  subgraph rules [规则层 — 唯一 parser/栈校验入口]
    KPS[knowledge_parser_service]
    UM[user_messages]
  end

  subgraph index [索引执行]
    KSJ[knowledge_sync_job_service]
    KLS[knowledge_library_service]
    PIS[pageindex_service]
  end

  subgraph qa [检索问答]
    KQS[knowledge_qa_service]
  end

  API[knowledge_embed.py API] --> KLS
  API --> KQS
  KLS --> KPS
  KLS --> PIS
  KSJ --> KPS
  KSJ --> KLS
  KSJ --> UM
  KQS --> KG
  KQS --> PIS
  KPS --> KG
  KG --> INT[knowflow_client / ragflow_*]
  PIS --> BR[pageindex_bridge]
```

**高内聚低耦合原则**：

- **KnowFlow 栈探活、客户端获取**：经 `knowledge.stack_reachable()` / `knowledge.client_for_user()`，不在各 service 写 `settings.knowflow_enabled and knowflow_stack_reachable()`。
- **Parser ID 默认值、PageIndex 判定、索引栈就绪**：经 `knowledge_parser_service`，不硬编码 `"pageindex"` / `"naive"`。
- **用户可见错误**：经 `user_messages.sanitize_user_message` 或 `background_job_error_message`。

---

## 2. KnowledgeGateway（`app/domains/knowledge/gateway.py`）

### 2.1 职责

Facade 模式：对外暴露稳定 API，内部 lazy import 具体 service，避免 `ragflow_sync` ↔ `ragflow_scope` 环依赖。

### 2.2 常用方法实现思路

| 方法 | 实现思路 |
|------|----------|
| `enabled()` | 读 `Settings.knowflow_enabled`，表示功能开关，**不**代表 API 可达 |
| `stack_reachable()` | 委托 `knowflow_stack_reachable()`：已 enabled 且 `RagflowClient().health_ok()` |
| `client_for_user(db, user)` | 按用户 RAGFlow 会话 / API Key 构造 `RagflowKnowflowClient`；无 KnowFlow 时返回 `LocalKnowflowClient` |
| `client_probe(user_id)` | 探活用，**不触发** RAGFlow 开户 |
| `sync_document(...)` | 委托 `sync_document_to_knowflow`：上传 bytes → dataset → parse |
| `reconcile_catalog(...)` | 对齐平台文件夹与 KnowFlow dataset 登记 |
| `meta_payload(...)` | 委托 `meta_service.build_rag_meta_payload` |

### 2.3 调用示例

```python
from app.domains.knowledge import knowledge

if not knowledge.stack_reachable():
    raise bad_request("知识服务不可用")

kf = knowledge.client_for_user(db, user)
```

---

## 3. 解析器规则层（`knowledge_parser_service.py`）

### 3.1 两套默认 parser

| 场景 | 配置项 | 默认 | 解析函数 |
|------|--------|------|----------|
| 上传 / 自动推断 | `KNOWLEDGE_DEFAULT_PARSER_ID` | `naive` | `parser_id_raw()` |
| 重新索引 | `KNOWLEDGE_REINDEX_DEFAULT_PARSER_ID` | `pageindex` | `reindex_parser_id_raw()` |

**为何分离**：上传需稳定向量分块；重新索引默认走结构索引（PageIndex），二者产品策略不同，共用一套默认会误伤上传路径。

### 3.2 核心函数实现思路

#### `parser_id_raw(parser_id)`

1. 若调用方传入非空字符串 → 去空格、小写后直接返回  
2. 否则读 `settings.knowledge_default_parser_id`，再 fallback `naive`  
3. **不做**白名单校验（由 `normalize_parser_id` 负责）

#### `reindex_parser_id_raw(parser_id)`

同上，但 fallback 链为 `knowledge_reindex_default_parser_id` → `PARSER_PAGEINDEX`。

#### `is_pageindex_parser(parser_id)`

**仅比较字面量** `(parser_id or "").strip().lower() == "pageindex"`。  
不经过 `parser_id_raw`，避免 `None` 被解析成 `naive` 导致误判。

#### `resolve_job_parser_id(payload)`

1. 读 `payload["mode"]`，默认 `"index"`（上传后索引）  
2. `mode == "reindex"` → `reindex_parser_id_raw(payload.get("parser_id"))`  
3. 否则 → `parser_id_raw(...)`  

**关键**：上传 Job 的 payload 通常无 `parser_id`，若误用 reindex 默认会得到 pageindex，故必须按 mode 分支。

#### `job_payload_uses_pageindex(payload)`

`is_pageindex_parser(resolve_job_parser_id(payload))`。  
供 `background_job_dispatch.dispatch_document_index_job` 决定是否跳过 Celery。

#### `index_stack_block_reason(parser_id, *, reindex=False)`

1. 按 `reindex` 标志选择 raw 解析函数，得到 `pid`  
2. 若 `is_pageindex_parser(pid)`：只检查 `pageindex_enabled`，通过则返回 `None`  
3. 否则：`knowledge.enabled()` → `"知识库同步未启用"`；`knowledge.stack_reachable()` → `"知识服务不可用..."`  
4. 全部通过返回 `None`  

API 层 `assert_index_stack_ready` 在此 reason 非空时 `raise bad_request(reason)`。

#### `infer_parser_for_upload_file(file_name, mime_type)`

1. 扩展名 + MIME 双判  
2. xlsx → `table`；ppt → `presentation`；图片 → `picture`  
3. 其余（pdf/doc/md/txt…）→ `normalize_parser_id(knowledge_default_parser_id)` + 默认 layout  
4. **不**自动选 PageIndex

#### `coerce_parser_layout(parser, layout)`

现代 OCR（PaddleOCR/MinerU/DOTS）需配合 smart/title/regex/parent_child；若用户选 naive + PaddleOCR，自动把 parser 提升为 `smart`，减少 KnowFlow 解析失败。

#### `build_parser_config(parser_id, layout_recognize, ...)`

1. PageIndex → 返回 `("pageindex", {"index_engine": "pageindex"})`，不调 KnowFlow  
2. 其它 → `coerce_parser_layout` + 深拷贝 `_PARSER_DEFAULTS[parser]` + 写入 `chunk_token_num` / `layout_recognize`

#### `list_parser_options()`

组装 `CHUNK_METHODS`、`LAYOUT_RECOGNIZERS` 与 `defaults`（**重索引默认** parser/layout）。  
前端 `useDocumentReindex.loadParserOptions()` 拉取后写入 `parserId` ref。

---

## 4. 索引流程

### 4.1 上传后首次索引

```mermaid
sequenceDiagram
  participant Upload as post_upload
  participant Dispatch as background_job_dispatch
  participant Job as knowledge_sync_job_service
  participant KF as KnowFlow

  Upload->>Dispatch: dispatch_post_upload_processing
  Note over Upload: 可能 schedule_knowledge_index_after_upload
  Dispatch->>Job: run_document_knowledge_index_job
  Job->>Job: resolve_job_parser_id (mode=index)
  Job->>Job: index_stack_block_reason
  Job->>KF: sync + parse + parse_watch
```

**实现要点**：

- Job payload：`mode` 缺省为 `index`，无 `parser_id` 时用上传默认 naive  
- OCR 失败：` _maybe_fallback_plain_text_parse` 先 DeepDOC，再 Plain Text（保留引用截图能力）

### 4.2 重新索引

```mermaid
sequenceDiagram
  participant FE as DocumentDetailView
  participant API as reindex_document
  participant Job as enqueue_document_reindex
  participant Exec as execute_document_reindex

  FE->>API: POST reindex (parser_id 可选)
  API->>API: reindex_parser_id_raw + assert_index_stack_ready
  API->>Job: 创建 mode=reindex Job
  Job->>Exec: run_document_knowledge_index_job
  alt PageIndex
    Exec->>Exec: execute_pageindex_reindex
  else KnowFlow
    Exec->>Exec: change_parser + parse (+ 可选 resync)
  end
```

**`execute_document_reindex` 实现思路**：

1. `reindex_parser_id_raw(parser_id)` 归一化  
2. PageIndex → 直接 `execute_pageindex_reindex`（不经 KnowFlow）  
3. KnowFlow 路径：判断是否需要 `resync`（md 索引、block 派生、dataset 缺失等）  
4. `change_document_parser` + `parse_documents` + 更新 `RagflowDocumentVersionLink`

**`create_document_reindex_job` 实现思路**：

- 启动前 `index_stack_block_reason(parser_id, reindex=True)`，不可用则**不创建** Job（PageIndex 在 KnowFlow 关闭时仍可创建）  
- payload 写入已解析的 `parser_id` 字符串，供 Worker 只读

### 4.3 PageIndex 结构索引（`pageindex_service.py`）

**`execute_pageindex_reindex` 实现思路**：

1. `assert_index_stack_ready(PARSER_PAGEINDEX)`  
2. 校验文件格式（`is_pageindex_supported_file`）  
3. `read_document_file_bytes` → `prepare_pageindex_index_path`（必要时转 md）  
4. `index_file_with_pageindex` → 本地 workspace 存 JSON 树  
5. `_upsert_version_link` 写 `PageindexVersionLink`（与 KnowFlow link 并行存在）

**检索引擎选择**（`resolve_retrieval_engine_for_document`）：

- 比较 PageIndex link 与 KnowFlow link 的 `index_completed_at`，取较新者  
- `effective_retrieval_engine` 再考虑 `pageindex_retrieval_available()`（LLM 是否配置）

---

## 5. 知识问答（`knowledge_qa_service.py`）

### 5.1 `retrieve_hits_for_qa` 实现思路

1. `validate_document_scope` 过滤无权文档  
2. `partition_documents_by_retrieval_engine` → PageIndex / KnowFlow / 不可检索  
3. PageIndex 文档：`pageindex_tree_search`（LLM 选 node_id → 取正文片段）  
4. KnowFlow 文档：`knowledge.stack_reachable()` 且 client enabled → 向量检索；否则 `_local_retrieve`  
5. 合并 hits，可选 `merge_nearby_retrieval_hits`，截断 `top_k`

### 5.2 流式问答错误处理

`_resolve_qa_session` 抛 `HTTPException` 时，用 `http_exception_message(exc, fallback=KNOWLEDGE_SERVICE_UNAVAILABLE)` 写入 SSE JSON，与 REST API 文案一致。

---

## 6. 配置项

| 环境变量 | 含义 | 默认 |
|----------|------|------|
| `KNOWFLOW_ENABLED` | KnowFlow 功能总开关 | — |
| `KNOWLEDGE_DEFAULT_PARSER_ID` | 上传/推断默认分块 | `naive` |
| `KNOWLEDGE_REINDEX_DEFAULT_PARSER_ID` | 重新索引默认分块 | `pageindex` |
| `KNOWLEDGE_DEFAULT_LAYOUT_RECOGNIZE` | PDF OCR 引擎 | `DeepDOC` |
| `PAGEINDEX_ENABLED` | 结构索引开关 | — |
| `PAGEINDEX_WORKSPACE_DIR` | 树索引本地目录 | `platform/.run/pageindex` |

---

## 7. 前端协作

| 模块 | 职责 |
|------|------|
| `api/knowledge.js` | `fetchParserOptions`、`reindexDocument`（parser_id 可选，默认由后端 Schema 填充） |
| `composables/useDocumentReindex.js` | 弹窗、轮询 Job / parse_status |
| `utils/knowledgeCitation.js` | PageIndex / KnowFlow 引用跳转 |
| `composables/usePlatformUi.js` | 统一 toast，错误经 `sanitizeUserFacingMessage` |

---

## 8. 相关文档

- [分层架构](../development/layered-architecture.md)
- [异步任务](async-and-jobs.md)
- [应用服务与域](backend-implementation.md)
- [前端结构](frontend-implementation.md)
- [知识数据一致性](../operations/knowledge-data-consistency.md)
