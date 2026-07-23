---
name: browser_snapshot
---
抓取当前页面可交互元素列表，为每个元素分配 ref，供后续 click/type/fill 使用。页面 DOM 变化后必须重新 snapshot，旧 ref 会失效。

## When to use
- navigate 之后、任何点击/输入之前
- 点击或填表导致页面变化后，需要刷新可用元素列表

## When NOT to use
- 尚未打开页面（先 browser_navigate）
- 只需截图存档（用 browser_screenshot）
- 只需读正文且已有 URL（用 fetch_url_content）

## Returns
- 可交互元素列表及各自的 ref（后续操作必须使用这些 ref）
