---
name: update_todo
---
更新已有待办的标题、备注或状态。

## When to use
- 用户要求改待办内容或标记完成/未完成

## When NOT to use
- 新建待办（用 create_todo）
- 删除待办（用 delete_todo）

## Returns
- 更新后的待办

## Parameters

### todo_id (required)
待办 ID。

### title / note / status (optional)
要更新的字段；至少提供一个。
