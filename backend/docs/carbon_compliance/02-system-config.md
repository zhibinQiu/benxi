# 系统后台可配置参数

配置表：`platform_carbon_strategy_settings`（单例 `id=1`，JSONB `payload`）。  
API：`GET/PUT /api/v1/carbon-assistant/settings`（写操作需 `admin.user`）。

默认值见 `app.services.carbon_compliance.defaults.default_settings()`。

## 1. 合规阈值 `compliance`

| 键 | 含义 | 默认 |
|----|------|------|
| `ccer_max_ratio` | CCER 最大抵扣比例 | 0.05 |
| `clearance_warn_days` | 清缴预警梯度（天） | [90, 30, 15] |
| `price_low_percentile` / `price_mid_percentile` | 碳价低/中位分位边界 | 0.30 / 0.70 |
| `single_trade_cap_default` | 默认单笔上限（吨） | 100000 |
| `annual_position_cap_default` | 默认年持仓上限 | 1000000 |
| `large_trade_split_threshold` | 大额拆分建议阈值 | 50000 |

## 2. 策略偏好 `strategy_profiles`

按企业 `risk_profile` 匹配：

| 画像 | 行为摘要 |
|------|----------|
| conservative | 不囤货、不卖富余、仅用自有 CCER、不主动推绿电/绿证 |
| balanced | 低位分批购配额、尽量用满 5% CCER、测算直购绿电 |
| aggressive | 高位卖富余、低位适度囤存、可推绿电与绿证 |

各画像布尔开关：`allow_stockpile`、`allow_sell_surplus`、`allow_buy_external_ccer`、`recommend_green_power`、`recommend_green_cert`。

## 3. 成本测算 `cost`

| 键 | 含义 |
|----|------|
| `listing_fee_rate` | 挂牌手续费率（单边）；手续费=成交总额×费率 |
| `block_fee_rate` | 大宗手续费率（单边）；线下撮合按此计 |
| `trade_fee_rate` | 旧字段：未填挂牌/大宗时回退 |
| `tax_rate` | 税费参数 |
| `grid_emission_factor` | 默认电网排放因子（tCO₂/MWh） |
| `green_abatement_factor` | 绿电减排折算系数 |
| `overdue_penalty_per_t` | 逾期罚款单价 |
| `holding_cost_annual_rate` | 资金占用年化 |

## 4. 行业参数 `industry_params`

按 `power` / `steel` / `cement` / `aluminum` 分桶：基准线、产能系数、发放月、结转、清缴月-日、罚金、电网因子。

## 5. 外部接口 `integrations`（可选）

| 键 | 含义 |
|----|------|
| `market_sync_period` | day / month / hour | day |
| `market_sync_enabled` | 是否启用后台自动同步 | true |
| `last_sync_at` | 最近一次同步时间（系统写入） | — |
| `erp_api_url` / `erp_api_key` | ERP 对接预留 | 空 |
| `excel_import_enabled` | Excel 批量导入开关 | true |

启动后后台每小时检查一次；到期则优先拉取上海环交所全国碳市场 K 线：

- 日线 `https://www.cneeex.com/zhhq/jsonData/hiskline.json?[ms_ts]`
- 分时 `https://www.cneeex.com/zhhq/jsonData/kline.json?[ms_ts]`

按自然月聚合后 upsert 到 `carbon_market_cea_monthly`。CCER 仍从碳中和网 HTML 补充。也可调用 `POST /api/v1/carbon-assistant/market/sync` 立即同步。
