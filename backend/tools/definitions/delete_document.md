---
name: delete_document
---
删除文档库中的文档。破坏性操作，必须 confirm=true。

## When to use
- 用户明确要求删除某文档，并已确认

## When NOT to use
- 用户未明确确认删除意图
- 仅移出文件夹（用 move_document）

## Returns
- 删除结果

## Parameters

### document_id (required)
文档 ID。

### confirm (required)
必须为 true 才会执行删除。
