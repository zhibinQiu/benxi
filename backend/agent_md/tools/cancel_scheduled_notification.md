---
name: cancel_scheduled_notification
---
取消一条尚未发送的定时通知。
需要传 notification_id（来自 list_scheduled_notifications 或 schedule_notification 的返回）。

## When to use
- 用户说「取消提醒」「取消定时通知」「删除提醒」
- 用户想取消之前设定的某个定时通知

## When NOT to use
- 通知已发送（无法取消）
- 未提供 notification_id

## Returns
- 取消结果（成功或失败原因）

## Parameters

### notification_id (required)
定时通知的唯一标识。
来自 list_scheduled_notifications 或 schedule_notification 的返回结果。
