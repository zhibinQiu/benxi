---
name: finance_search
---
搜索中国 A 股股票或公募基金。输入关键词（名称或代码），返回匹配的证券列表。

## When to use
- 需要查找股票代码（如输入"贵州茅台"得到 600519）
- 需要查找基金代码
- 不确定完整代码时模糊搜索

## Parameters

### query (required)
搜索关键词，可以是股票名、基金名或代码片段。

### market (optional)
搜索市场类型：
- `stock` — 搜索 A 股股票（默认）
- `fund` — 搜索公募基金

## Returns
- 匹配结果列表，每项包含：code（代码）、name（名称）、type（类型）
