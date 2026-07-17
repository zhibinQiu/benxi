---
name: carbon-consulting
description: "从官方渠道获取双碳领域实时信息：碳市场行情（CEA/CCER/EUA）、政策法规、排放数据、CCER 项目、国际碳价、地方双碳方案"
use_when: "用户询问碳价行情/碳交易/双碳政策/CCER 项目/碳排放核算/碳中和/碳达峰/国际碳市场/EU ETS 等双碳问题"
dont_use_when: "非双碳领域的通用问答、常识问答、平台业务操作"
output: "从对应官方源获取的结构化摘要信息，附 URL 与数据说明"
---

# 双碳咨询获取

## 查询类型与数据源

| 类型 | 说明 | 主要数据源 |
|------|------|-----------|
| `price` | **碳价行情**：CEA 碳价、CCER 行情、各地试点碳价 | cets.org.cn, cneeex.com, tanpaifang.com |
| `policy` | **政策法规**：双碳顶层设计、行业方案 | gov.cn, ndrc.gov.cn, mee.gov.cn, miit.gov.cn |
| `emission` | **排放数据**：企业碳排放、核算标准 | ipe.org.cn, ccchina.org.cn, eco.gov.cn |
| `ccer` | **CCER 数据**：方法学、项目备案、签发 | cneeex.com, chinacrc.net.cn |
| `international` | **国际碳市场**：EUA 碳价、自愿碳市场 | carbon-pulse.com, eex.com, climateimpactx.com |
| `local` | **地方双碳方案**：省市碳达峰方案 | ccnt.igdp.cn, 3060.org.cn |
| `news` | **碳新闻资讯**：每日碳新闻、政策解读 | cenews.com.cn, tandao.org, 3060.org.cn |

## 用法

```
run_skill_script carbon-consulting <类型> [关键词/URL]
```
