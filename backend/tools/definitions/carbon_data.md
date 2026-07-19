---
name: carbon_data
---
从官方渠道获取双碳结构化数据摘要（非新闻）。

按 topic 选择数据域：
- emission：企业碳排放、核算标准（ipe.org.cn、ccchina.org.cn 等）
- ccer：方法学、项目备案、签发（cneeex.com、chinacrc.net.cn）
- international：EUA / 自愿碳市场（carbon-pulse.com、eex.com、CIX）
- local：省市碳达峰方案（ccnt.igdp.cn、3060.org.cn）

## When to use
- 查询排放核算、CCER 项目、国际碳价、地方双碳方案等结构化数据
- 需要附官方来源的事实底稿

## When NOT to use
- 碳价行情快照（用 carbon_price）
- 政策法规原文摘要（用 carbon_policy）
- 每日碳新闻/资讯（用浏览器：`invoke_context_subagent(kind=execute)`）

## Parameters

### topic (required)
数据主题：`emission` / `ccer` / `international` / `local`

### keyword (optional)
可选关键词，缩小摘要关注点。

### url (optional)
指定 URL 直接抓取。

## Returns
- summary_md：多源摘要 Markdown
- sources：各源 title / snippet / extracted
- queried_at：查询时间
