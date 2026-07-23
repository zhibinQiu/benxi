---
name: read_document_content
---
读取平台文档库中指定文档的解析正文（当前版本）。可通过 document_id 或 document_name 定位。

## When to use
- 用户指定了某份文档，需要阅读/总结其内容
- 已从 search_documents_by_name / list_* 拿到 document_id

## When NOT to use
- 按语义检索知识库（用 knowledge_retrieve）
- 读取公开网页（用 fetch_url_content）
- 文档尚未解析完成时可能内容不完整

## Returns
- 文档解析正文（可截断至 max_chars）

## Parameters

### document_id (optional)
文档 ID；与 document_name 至少填一个。

### document_name (optional)
文档标题；与 document_id 至少填一个。优先用 ID 更准确。

### max_chars (optional)
最大返回字符数，默认 16000，范围 500–80000。
