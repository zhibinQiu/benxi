# 前端结构

> 说明书 · 第四篇 §4.1 · [开发实现说明书总览](../development/implementation-manual.md)

---

## 1. 目录职责

```
platform-frontend/src/
  api/
    http.js           # Token、api()、错误解析 — 所有 REST 根基
    documents.js      # 文档库
    knowledge.js      # 知识检索 / 重新索引 / 问答
    client.js         # 聚合 re-export（兼容旧 import）
  composables/
    usePlatformUi.js  # 统一 toast / 确认框（唯一推荐入口）
    useDocumentReindex.js
  views/              # 路由页，组合 composable + api
  utils/
    uiMessage.js      # sanitizeUserFacingMessage、notifyDeduped
    knowledgeCitation.js
    knowledgeIndex.js
```

**原则**：`views` 不直接 `fetch`；`api/*` 不含 UI 状态；用户反馈只走 `usePlatformUi`。

---

## 2. HTTP 层（`api/http.js`）

### 2.1 `api(path, options)` 实现思路

1. 拼接 `getApiBase()` + path  
2. 自动附加 `Authorization: Bearer`（若有 token）  
3. `parseResponse`：非 2xx 抛 Error，message 来自后端 `detail.message`  
4. 开发态默认走同源 `/ai` 反代，避免浏览器直连 `127.0.0.1:18000` 不可达  

### 2.2 `bootstrapClientConfig`

应用启动时拉 `GET /system/client-config`，可覆盖 `api_base`（多域名部署）。

---

## 3. UI 反馈（`usePlatformUi.js`）

### 3.1 为何统一

- 与后端 `user_messages.sanitize_user_message` 对齐，过滤 RAGFlow/PageIndex 等内部词  
- `notifyDeduped`：2.2s 内相同文案不重复弹  
- 鉴权静默错误经 `authError.js` 过滤，避免登出时刷屏  

### 3.2 方法实现思路

| 方法 | 思路 |
|------|------|
| `success/warning/info` | `resolveText`（i18n key 或原文）→ `notifyDeduped` |
| `error` | 对象取 `.message` → `sanitizeUserFacingMessage`；鉴权错误直接 return |
| `confirmDelete` | 非 blocking 模式：先 toast「删除中」，异步 `onPositive`，失败 `error(e)` |

`useUiMessage.js` 已废弃，仅为 `usePlatformUi` 的 re-export，新代码勿引用。

---

## 4. 知识检索相关

### 4.1 `api/knowledge.js`

| 函数 | 实现思路 |
|------|----------|
| `fetchParserOptions` | `GET /knowledge/parsers` → 含 `defaults.parser_id`（后端重索引默认） |
| `reindexDocument` | `POST .../reindex`；`parser_id` 仅在有值时写入 body，否则由后端 Schema `default_factory` 填充 |
| `knowledgeQaChatSend` | 无 session 时先 `createKnowledgeQaSession` |

### 4.2 `useDocumentReindex.js`

1. **`loadParserOptions`**：拉后端 defaults，写入 `parserId` / `layoutRecognize`（初始 ref 为空字符串，避免与后端配置漂移）  
2. **`submitReindex`**：调 API → 若有 `knowledge_job_id` 则 `subscribePlatformJobEvents`，否则轮询 `parse_status`  
3. **`isStaleFailureStatus`**：刚提交时忽略旧的「解析失败」状态，避免误报  

### 4.3 `utils/knowledgeCitation.js`

按 `citation.source`（`pageindex` | `knowflow`）生成预览 URL 与文档详情锚点；与后端 `knowledge_qa_service`  citation 结构对齐。

### 4.4 `utils/knowledgeIndex.js`

`isDocumentIndexReady`：`knowledge_synced` 且 `parse_status` 为「已完成/已索引」。供 scope 树与检索面板展示 Tag。

---

## 5. 路由与功能插件

- 系统功能卡片：`GET /system/features` → `SystemFunctionsView`  
- 知识检索：`feature id = knowledge_search`，路由 `knowledge-search`  
- 历史路径 `/system/pageindex` 重定向到 `knowledge-search`（书签兼容，**无**独立 PageIndex 功能卡片）

插件 id 与路由 path 对齐表见 [分层架构 §4 迁移清单](../development/layered-architecture.md)。

---

## 6. 相关文档

- [知识服务实现](knowledge-implementation.md)
- [API 与约定](api-conventions.md)
- [功能插件](../platform/feature-plugins.md)
