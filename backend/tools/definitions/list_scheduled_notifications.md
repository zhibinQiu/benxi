---
name: list_scheduled_notifications
---
查看当前用户所有待发送的定时通知列表（未发送、未取消的）。

## When to use
- 用户问「有哪些定时通知」「查看我的提醒」「列出定时任务」
- 需要获取 notification_id 以便取消某个定时通知

## When NOT to use
- 查看已发送或已取消的通知（它们不会出现在结果中）
- 查看系统通知历史（通知在系统通知中心查看）

## Returns
- 待发送通知列表（通知标题、计划发送时间等）
- 已发送或已取消的通知不会出现在结果中

## Parameters

### limit (optional)
最大返回条数。默认 20，最大 50。
