---
name: web_search
---
联网检索公开信息，返回各来源全文（Markdown）。
可多次调用此工具实现多轮搜索：先宽泛搜索了解概貌，根据已读全文生成更具体的关键词继续深挖。

## When to use
- 最新政策/行情/新闻/价格或需联网检索公开信息
- 需要多轮搜索：先宽泛搜索了解概貌，再根据已读全文生成更具体的关键词继续深挖
- 不同来源结论矛盾时追加搜索做交叉验证

## When NOT to use
- 企业内部知识库检索（用 knowledge_retrieve）
- 用户已提供 URL（用 fetch_url_content）
- 知识图谱查询（用 kg_query）

## Returns
- 搜索引擎摘要 + 前 N 条全文（Markdown 格式）
- read_full=0 仅返回摘要片段（省 Token），默认 3 条全文

## Parameters

### query (required)
搜索关键词。

### max_items (optional)
最大结果数，默认 8，最大 20。

### read_full (optional)
读取前 N 条链接的全文（Markdown）。0=仅返回搜索引擎摘要。默认 3，最大 6。
