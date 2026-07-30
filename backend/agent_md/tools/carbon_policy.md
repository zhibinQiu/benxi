---
name: carbon_policy
---
从发改委智能云搜索获取双碳政策法规，并抓取详情页正文全文。

数据源：https://so.ndrc.gov.cn/（siteCode=bm04000007）。返回政策列表、发布时间、来源与正文全文。

## When to use
- 查询碳达峰/碳中和顶层文件、"1+N" 政策
- 查询碳市场条例、行业降碳方案、能耗双控政策
- 需要附官方来源的政策事实底稿（含全文）

## When NOT to use
- 每日新闻滚动、媒体政策解读（用浏览器：`invoke_context_subagent(kind=execute)` 打开 cenews/tandao/3060 等）
- 实时碳价（用 carbon_price）

## Parameters

### keyword (optional)
搜索关键词，默认「碳」。如「钢铁纳入碳市场」「碳达峰方案」。

### url (optional)
指定政策详情页 URL，直接抓取全文；留空则按 keyword 搜索。

## Returns
- summary_md：含正文全文的 Markdown
- sources：各条 title / url / published_at / source / body
- queried_at：查询时间
- total_hits：上游命中总数
