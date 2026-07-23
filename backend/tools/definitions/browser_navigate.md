---
name: browser_navigate
---
在当前浏览器会话中打开指定 http/https 页面。典型流程的第一步：navigate → snapshot → click/type/fill。

## When to use
- 需要在真实浏览器中打开目标网址再交互
- 多步网页操作开始前先导航到入口页

## When NOT to use
- 只需读取公开页面正文（用 fetch_url_content）
- 只需搜索公开信息（用 web_search / invoke_context_subagent kind=search）
- 复杂自然语言端到端任务可优先 browser_run_task

## Returns
- 导航结果摘要（最终 URL、标题等）

## Parameters

### url (required)
目标地址，须为 http:// 或 https://。
