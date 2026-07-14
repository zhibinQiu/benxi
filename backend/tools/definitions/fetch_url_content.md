---
name: fetch_url_content
---
获取指定 URL 的网页正文内容（Markdown 格式）。
与 web_search 不同：此工具直接读取给定 URL 的内容，不执行搜索。
适合用户已提供链接、需要阅读页面全文的场景。

## When to use
- 用户已提供 URL，需要读取页面全文
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
