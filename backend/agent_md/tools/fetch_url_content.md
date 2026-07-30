---
name: fetch_url_content
---
获取指定 URL 的网页正文内容（Markdown 格式）。

**阅读策略：先概要，再择需读全文。**
先用 `web_search(read_full=0)` 获取摘要片段，如果
摘要不足以回答问题时，再对特定 URL 用此工具获取全文。

## When to use
- 用户已提供 URL，需要读取页面全文
- 从 web_search 的摘要片段判断某个链接内容很重要，需要读全文
- 需要获取某个具体页面的完整正文内容

## When NOT to use
- 需要搜索公开信息（用 web_search）
- URL 需要登录才能访问（不支持登录态页面）

## Returns
- 网页正文 Markdown 内容

## Parameters

### url (required)
目标网页 URL。仅限可公开访问的 URL。

### max_chars (optional)
最大返回字符数。默认 50000。
