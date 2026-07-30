---
name: stock_kline
---
获取中国 A 股历史 K 线数据，用于技术面分析。

返回 OHLC（开盘价、最高价、最低价、收盘价）和成交量。支持日 K、周 K、月 K 三种周期。

## When to use
- 需要获取个股的历史 K 线数据进行技术分析
- 查看价格趋势、支撑位、阻力位
- 结合技术指标（均线、MACD 等）分析

## Parameters

### code (required)
股票代码，如 600519、000001、300750。

### ktype (optional)
K 线周期类型。可选值：
- `day` — 日 K（默认）
- `week` — 周 K
- `month` — 月 K

## Returns
- 按时间降序排列的 K 线数据列表，每项包含：date、open、high、low、close、volume
