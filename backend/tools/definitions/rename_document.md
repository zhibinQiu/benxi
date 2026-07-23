---
name: rename_document
---
重命名文档库中的文档标题。

## When to use
- 用户要求改文档名称

## When NOT to use
- 移动到其他文件夹（用 move_document）
- 修改正文内容（用 create 新文档或其它编辑能力；本工具只改标题）

## Returns
- 更新后的文档元信息

## Parameters

### document_id (required)
文档 ID。

### new_title (required)
新标题。
