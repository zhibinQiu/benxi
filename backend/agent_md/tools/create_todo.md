---
name: create_todo
---
为当前用户创建一条待办事项。

## When to use
- 用户要求记待办、任务清单项
- 「帮我加一个待办：…」

## When NOT to use
- 定时提醒通知（用 schedule_notification）
- 立即站内通知（用 send_notification）
- 列出/更新/删除待办（用 list/update/delete_todo）

## Returns
- 新建待办 ID 与内容

## Parameters

### title (required)
待办标题。

### note (optional)
补充说明。
