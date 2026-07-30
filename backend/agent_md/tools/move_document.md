---
name: move_document
---
将文档移动到指定文件夹（可按 folder_id 或 folder_name）。

## When to use
- 用户要求把文档归入某文件夹

## When NOT to use
- 仅改标题（用 rename_document）
- 分享给他人（用 share_document）

## Returns
- 移动结果

## Parameters

### document_id (required)
文档 ID。

### folder_id / folder_name (optional)
目标文件夹；通常至少提供一个。
