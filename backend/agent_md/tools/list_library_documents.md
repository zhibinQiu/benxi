---
name: list_library_documents
---
按范围与可选文件夹/关键词列出文档库中的文档。

## When to use
- 「我的文档库有哪些文件」「某某文件夹下有什么」
- 浏览某 scope 下的文档清单

## When NOT to use
- 按标题模糊搜索（用 search_documents_by_name）
- 语义检索正文片段（用 knowledge_retrieve）
- 仅列出可管理/有权限操作的子集（用 list_manageable_documents）

## Returns
- 文档列表（标题、ID、文件夹等）

## Parameters

### scope (required)
文档范围，默认语义上常用 personal。

### folder_name / folder_id (optional)
限定文件夹；二者择一即可。

### keyword (optional)
标题关键词过滤。

### limit (optional)
默认 30，最大 100。
