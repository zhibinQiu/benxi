---
name: list_todos
---
列出当前用户的所有待办事项。支持按状态过滤。

## When to use
- 用户问「我的待办」「有哪些任务」「未完成的事项」
- 请提供您的待办事项筛选条件

## When NOT to use
- 创建待办（用 create_todo）
- 设置定时通知（用 schedule_notification）

## Returns
- 待办事项列表（标题、状态、创建时间）
