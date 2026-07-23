---
name: list_manageable_documents
---
列出当前用户有管理权限（可改名/移动/删除等）的文档。

## When to use
- 准备执行重命名、移动、删除、分享前，确认可操作文档
- 用户问「我能管理哪些文档」

## When NOT to use
- 仅浏览/阅读可见文档（用 list_library_documents）
- 语义检索（用 knowledge_retrieve）

## Returns
- 可管理文档列表

## Parameters

### keyword (optional)
标题关键词过滤。

### limit (optional)
默认 20，最大 100。
