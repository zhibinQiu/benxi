---
name: carbon_price
---
从官方渠道获取碳价行情摘要（全国 CEA、CCER、地方试点等）。

数据源优先：cets.org.cn、cneeex.com、tanpaifang.com。返回多源结构化摘要与 URL，禁止编造实时碳价。

## When to use
- 查询今日/近期全国碳市场 CEA 成交价、成交量
- 查询 CCER 或地方试点碳价
- 需要附官方来源的碳价事实底稿

## When NOT to use
- 每日碳新闻、政策解读、资讯滚动（用浏览器：`invoke_context_subagent(kind=execute)`）
- 非双碳领域的通用问答

## Parameters

### keyword (optional)
可选关键词，如「全国碳市场」「CCER」「广东试点」。

### url (optional)
指定官方 URL 直接抓取；留空则按默认碳价源查询。

## Returns
- summary_md：多源摘要 Markdown
- sources：各源 title / snippet / extracted
- queried_at：查询时间
