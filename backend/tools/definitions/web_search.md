---
name: web_search
---
【内部工具】联网检索公开信息，返回各来源全文（Markdown）。
此工具不直接暴露给用户对话，由 deep_research 子智能体内部调用。
可多次调用此工具实现多轮搜索：先宽泛搜索了解概貌，根据已读全文生成更具体的关键词继续深挖。

## When to use
- 仅供 deep_research 子智能体内部调用，不直接暴露给 LLM

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
