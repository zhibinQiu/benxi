---
name: search_documents_by_name
---
按文档标题关键词搜索当前用户可见的文档，返回匹配列表（含 document_id）。拿到 ID 后再用 read_document_content 读正文。

## When to use
- 用户说「找名叫…的文档」「有没有标题含…的文件」
- 已知部分文件名，需要定位 document_id

## When NOT to use
- 按内容语义检索知识库片段（用 knowledge_retrieve）
- 已知 document_id 直接读正文（用 read_document_content）
- 列出某文件夹下全部文档（用 list_library_documents）

## Returns
- 匹配文档列表（标题、ID、所在范围等）

## Parameters

### name (required)
标题关键词。

### scope (optional)
文档范围：personal / department / org 等（与平台文档库一致）。

### limit (optional)
最多返回条数，默认 20，最大 50。
