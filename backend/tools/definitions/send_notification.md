---
name: send_notification
---
立即发送一条系统站内通知给当前用户。
当用户要求「通知我」「提醒我」「发消息给我」时使用。

## When to use
- 用户要求立即发送站内通知
- 任务完成时需要即时通知用户

## When NOT to use
- 需要在指定未来时间发送（用 schedule_notification）
- 发送外部邮件、短信、第三方应用消息（不支持）
- 用户只是问问题、不需要触发通知

## Returns
- 通知 ID 和发送结果
- 用户将在通知中心查阅，不强制弹窗

## Parameters

### title (required)
通知标题，简短概括提醒内容。最长 200 字符。

### body (optional)
通知正文，补充说明提醒详情。最长 4000 字符。不需要时留空。

### link (optional)
点击通知后跳转的链接。不需要时留空。
