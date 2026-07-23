---
name: create_library_document
---
向文档库写入一篇新文档（默认 Markdown）。可选放入指定文件夹。

## When to use
- 用户要求把内容保存进文档库
- Agent 生成报告/笔记后落库

## When NOT to use
- 更新已有文档标题（用 rename_document）
- 仅检索已有知识（用 knowledge_retrieve）
- 上传型二进制大文件场景（本工具写入文本内容）

## Returns
- 新建文档 ID 与元信息

## Parameters

### title (required)
文档标题。

### content (required)
正文内容。

### scope (optional)
默认 personal。

### folder_id / folder_name (optional)
目标文件夹。

### description (optional)
文档简介。

### content_format (optional)
内容格式，默认 markdown。
