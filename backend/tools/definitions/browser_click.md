---
name: browser_click
---
在当前浏览器会话中，点击 `browser_snapshot` 返回的可交互元素。

典型流程：`browser_navigate` → `browser_snapshot` → `browser_click` / `browser_type` / `browser_fill`。

## When to use
- 点击链接、按钮、菜单、标签等可交互控件
- 已有有效的 snapshot ref

## When NOT to use
- 尚未 snapshot，或 ref_map 为空（先 browser_snapshot）
- 尚未打开页面（先 browser_navigate）
- 页面已变化仍使用旧 ref（重新 snapshot）
- 只需读公开网页正文（用 fetch_url_content）
- 复杂多步自然语言任务可考虑 browser_run_task

## Returns
- 点击后的页面状态摘要

## Parameters

### ref (required)
`browser_snapshot` 返回的元素引用 ID。页面变化后必须重新 snapshot 再使用新 ref。
