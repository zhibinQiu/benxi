---
name: carbon_policy
---
从官方渠道获取双碳政策法规摘要。

数据源优先：gov.cn、ndrc.gov.cn、mee.gov.cn、miit.gov.cn。返回多源结构化摘要与 URL。

## When to use
- 查询碳达峰/碳中和顶层文件、"1+N" 政策
- 查询碳市场条例、行业降碳方案、能耗双控政策
- 需要附官方来源的政策事实底稿

## When NOT to use
- 每日新闻滚动、媒体政策解读（用浏览器：`invoke_context_subagent(kind=execute)` 打开 cenews/tandao/3060 等）
- 实时碳价（用 carbon_price）

## Parameters

### keyword (optional)
可选关键词，如「钢铁纳入碳市场」「碳达峰方案」。

### url (optional)
指定政策页 URL；留空则按默认官方源查询。

## Returns
- summary_md：多源摘要 Markdown
- sources：各源 title / snippet / extracted
- queried_at：查询时间
