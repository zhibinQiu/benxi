---
name: browser_type
---
向 snapshot 返回的输入框元素键入文本；可选提交（如回车搜索）。

## When to use
- 向搜索框、单行输入框输入文字
- 需要输入后立即提交（submit=true）

## When NOT to use
- 多个表单字段批量填写（用 browser_fill）
- 没有有效 ref（先 browser_snapshot）
- 点击按钮/链接（用 browser_click）

## Returns
- 输入操作结果与页面状态摘要

## Parameters

### ref (required)
输入框的 snapshot ref。

### text (required)
要输入的文本。

### submit (optional)
是否在输入后提交（如按回车）。默认 false。
