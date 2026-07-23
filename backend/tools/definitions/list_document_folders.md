---
name: list_document_folders
---
列出指定范围下的文档库文件夹。

## When to use
- 创建/移动文档前需要知道有哪些文件夹
- 用户问「文档库文件夹结构」

## When NOT to use
- 列出文件夹内文档（用 list_library_documents）
- 知识库挂载查询（用 list_mounted_folders，若可用）

## Returns
- 文件夹列表（名称、ID 等）

## Parameters

### scope (required)
文档范围（personal / department / org 等）。
