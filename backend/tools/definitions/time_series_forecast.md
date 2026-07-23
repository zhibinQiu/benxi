---
name: time_series_forecast
---
时序预测模型推理：基于历史日线外推至年底（中枢价与高低带）。

算法由 `method` 选择（rule / ets / sarimax / prophet）；内置序列由 `series` 选择（cea / ccer）。
用于走势预测与至年底外推，不是实时行情摘要。

## When to use
- 用户询问「碳价会涨到多少」「预测到年底」「外推走势」
- 需要比较不同预测算法（规则 / ETS / SARIMAX / Prophet）的结果
- 履约策略讨论需要年底价锚点

## When NOT to use
- 今日/近期实时碳价行情摘要（用 carbon_price）
- 政策法规查询（用 carbon_policy）
- 排放/CCER 项目/国际市场结构化摘要（用 carbon_data）

## Parameters

### method (optional)
预测算法，默认 `rule`：
- `rule`：衰减趋势 + 去均值季节 + 履约季冲高回落
- `ets`：Holt-Winters 加法季节（交易周 period=5）
- `sarimax`：带履约月(10–12)外生变量的 SARIMAX/ARX
- `prophet`：周/年季节性 + 履约月回归器

### series (optional)
内置序列，默认 `cea`：
- `cea`：全国碳市场配额日线
- `ccer`：自愿减排量日线

## Returns
- summary：年底价、高低带、峰谷与交易日数
- forecast_sample：预测序列抽样点（首/中/末）
- method / series / source_name：算法、序列与数据来源
