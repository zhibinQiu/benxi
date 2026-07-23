# 模块对应关系

| 业务模块 | 表 / 配置 | 引擎 / 服务 | API | 前端 |
|----------|-----------|-------------|-----|------|
| 基础数据管理 | `carbon_enterprises`、排放/预测表、三类台账 | `carbon_compliance_service` CRUD | `/enterprises/*` | Tab「企业档案」「排放与资产」 |
| 政策规则配置 | `platform_carbon_strategy_settings` | `defaults` + settings service | `/settings` | Tab「市场与规则」 |
| 市场数据管理 | `carbon_market_*_monthly` | market CRUD；可选 `carbon_service` 摘要 | `/market/*`、`/trading/*` | Tab「市场与规则」 |
| 碳排放量核算 | 读取排放+绿电+CEA | `carbon_compliance/accounting.py` | 策略 run 内嵌 | 策略页快照 |
| 策略推荐引擎 | `carbon_strategy_runs` | `strategy_engine.py` + `market_cycle.py` | `/strategy/run` | Tab「策略推荐」 |
| 合规校验 | 配置 `compliance` | `compliance.py` | run 内嵌 | 方案过滤结果 |
| 报表与预警 | `carbon_alerts`、run.report_md | `alerts.py`、`report_export.py` | `/alerts`、导出 | Tab「预警中心」 |

Feature：`carbon_assistant`，路由 `/system/carbon-assistant`，权限 `feature.carbon_assistant`。
