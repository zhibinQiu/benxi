---
name: web_search
---
【内部工具】联网检索公开信息，返回各来源全文（Markdown）。

**阅读策略：先概要，再择需读全文。**
先调 `web_search(read_full=0)` 获取摘要片段快速判断是否够用；
如摘要不足以回答问题，再对特定 URL 调 `fetch_url_content` 获取全文。

## When to use
- 检索公开网络信息
- 先 read_full=0 看摘要，再择需 fetch_url_content
- 如需自动读前 N 条全文，设置 read_full=3~6

## Returns
- 搜索引擎摘要 + 前 N 条全文（Markdown 格式）
- read_full=0 仅返回摘要片段（省 Token），默认 3 条全文

## Parameters

### query (required)
搜索关键词。

### max_items (optional)
最大结果数，默认 8，最大 20。

### read_full (optional)
读取前 N 条链接的全文（Markdown）。0=仅返回搜索引擎摘要（秒级返回）。默认 3，最大 6。
