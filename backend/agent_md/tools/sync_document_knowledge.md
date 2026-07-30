---
name: sync_document_knowledge
---
将指定文档同步到知识库，使其可被 knowledge_retrieve 检索。

## When to use
- 新写入或更新的文档需要进入知识检索
- 用户问「为什么知识库搜不到刚上传的文档」时触发同步

## When NOT to use
- 仅阅读文档正文（用 read_document_content）
- 索引损坏需强制重建（用 reindex_document）

## Returns
- 同步任务/状态摘要

## Parameters

### document_id (required)
文档 ID。
