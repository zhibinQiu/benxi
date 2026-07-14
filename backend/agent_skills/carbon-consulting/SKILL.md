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

### 示例

| 命令 | 说明 |
|------|------|
| `carbon-consulting price` | 查全国碳价行情 |
| `carbon-consulting policy` | 查最新双碳政策 |
| `carbon-consulting news` | 查碳新闻资讯 |
| `carbon-consulting price https://www.cets.org.cn/xxx` | 查指定 URL 的碳价 |
| `carbon-consulting policy 钢铁纳入碳市场` | 查特定政策（关键词用于后续 web_search） |

## 功能特性

1. **多源并行**：每个类型查询自动尝试多个数据源，连接失败的源静默跳过
2. **智能解析**：针对碳价、政策等不同类型数据做专门的文本提取
3. **错误容错**：单个数据源不可用不影响整体结果

## 完整数据源清单

### 官方政策渠道

| 来源 | 网址 | 核心内容 |
|----------|------|----------|
| 中国政府网 | https://www.gov.cn | 中央双碳顶层文件、"1+N"双碳政策 |
| 国家发改委 | https://www.ndrc.gov.cn | 碳达峰行动方案、能耗双控 |
| 生态环境部 | https://www.mee.gov.cn | 碳市场、CCER 方法学、核算指南 |
| 工信部 | https://miit.gov.cn | 工业零碳、绿色工厂 |
| 全国碳市场信息网 CETS | https://www.cets.org.cn | CEA 碳价、成交量、CCER 行情 |
| 中国气候变化信息网 | https://www.ccchina.org.cn | 气候政策、IPCC 报告 |

### 碳价与交易数据

| 平台 | 网址 | 内容 |
|------|------|------|
| 上海环境能源交易所 | https://www.cneeex.com | CEA 每日实时价格、CCER 交易行情 |
| 中国碳排放权注册登记结算公司 | https://www.chinacrc.net.cn | 企业碳账户、配额数据 |

### 综合碳资讯

| 平台 | 网址 | 内容 |
|------|------|------|
| 中国环境网·碳引擎 | https://www.cenews.com.cn | 每日碳新闻、政策解读 |
| 碳中和网（3060） | https://www.3060.org.cn | 国家/省市政策汇编 |
| 零碳录（iGDP） | https://ccnt.igdp.cn | 各省市碳达峰方案 |
| 碳道 | https://www.tandao.org | 每日碳价分析、CCER 动态 |

### 国际碳市场

| 平台 | 网址 | 内容 |
|------|------|------|
| Carbon Pulse | https://carbon-pulse.com | 欧盟碳价、国际 CCER |
| Climate Impact X (CIX) | https://climateimpactx.com | 全球自愿碳市场价格 |
| 欧洲能源交易所 EEX | https://www.eex.com | EU ETS：EUA 实时行情 |

## 约束

- 碳价等实时数据必须从上述源获取，禁止编造
- 区分全国 CEA / 地方试点 / CCER 不同价格体系
- 数据源连接失败时如实报告，不提供替代服务
