---
name: stock_quote
---
获取中国 A 股实时行情数据。

返回最新价、涨跌幅（%）、涨跌额、开盘价、最高价、最低价、昨收价、成交量（手）、成交额、市盈率、振幅、流通市值、总市值等指标。可一次查询多只股票（逗号分隔多个代码）。

## When to use
- 需要获取 A 股股票的实时价格和常用指标（PE、涨幅、成交量等）
- 查看个股盘口快照数据
- 批量查询多只股票对比

## Parameters

### codes (required)
股票代码，逗号分隔多个。例如：`600519,000001,300750`

不区分交易所前缀，直接输入纯数字代码即可。

## Returns
- 每只股票的实时行情：code、name、price、change、change_pct、open、high、low、prev_close、volume、turnover、pe、amplitude、market_cap
