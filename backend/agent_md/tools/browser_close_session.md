---
name: browser_close_session
---
关闭当前对话绑定的浏览器会话，释放页面与资源。

## When to use
- 浏览器任务已完成，不再需要该会话
- 用户明确要求关闭浏览器

## When NOT to use
- 后续还要继续在同一页面操作
- 任务中途（关闭后需重新 navigate）

## Returns
- 会话关闭确认
