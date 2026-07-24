# Agents 路由目录（调度层只读 · 动态注入依据）

> 本文件是专精分配的**唯一业务偏好来源**。调度 LLM / 展示层只注入本文，勿在代码中写死领域规则。

## orchestrator
- Title: 小析
- Use when: 日常编排与通用能力 — 联网检索、外部新闻/资讯、浏览器站点搜索/截图/打开网页、图表绘制、AI 对话/生图/识图；父层仅见已挂载工具与技能，执行交给子智能体或专精 Agent
- Don't use when: 平台文档/待办/通知/用户部门 CRUD（platform）、正式长报告（report）、Skill 创建修改删除（skill-dev）、双碳专业分析（carbon）、电力经济（power-economy）、股市深度分析（stock）
- Skills: knowledge-qa；其余仅已挂载（find_skills）；执行用 `invoke_context_subagent`
- Tools: 已挂载原子工具（检索/本体/通知/browser_* 等，以 binding 为准）

## platform
- Title: 平台操作
- Use when: 文档库 CRUD、待办 CRUD、系统通知（发送/定时/提醒）、用户/部门/组织查询与管理
- Don't use when: 外部新闻/联网检索、通用问答、AI 生图、浏览器网页操作、Skill 开发
- Tools: 文档库/待办/通知/用户部门管理/记忆等原子工具

## report
- Title: 撰写报告
- Use when: 撰写/扩写/生成可研、方案、计划书、调研/测试/工作类长文档
- Don't use when: 简单短问答、平台信息操作、图表绘制
- Skills: report-*（发展 Skill 白名单，动态挂载）
- Tools: `web_search` / `knowledge_retrieve` / `fetch_url_content` / 记忆

## skill-dev
- Title: 技能开发
- Use when: 创建/修改/删除上传型 Skill、run_skill_script 验证、编写网页抓取/自动化脚本包；抓取类 Skill 可用浏览器调研页面结构作为中间步骤
- Don't use when: 纯浏览器操作、普通问答（orchestrator）
- Skills: skill-development（动态挂载）
- Tools: Skill 管理 / 浏览器 / `web_search` / `knowledge_retrieve` / 记忆

## carbon
- Title: 双碳智能体
- Use when: 双碳领域 — 碳市场行情、碳交易规则、碳中和/碳达峰、CCER、碳排放核算、双碳政策解读与行业新闻分析
- Don't use when: 非双碳问题；浏览器站点搜索/截图等页面操作（orchestrator，即使主题含双碳）
- Skills: carbon-qa（ask 编排 carbon_price/carbon_policy/carbon_data；资讯走浏览器 execute）
- Tools: carbon_price / carbon_policy / carbon_data / time_series_forecast；`web_search` / `knowledge_retrieve` / `kg_query` / `fetch_url_content` / 记忆

## power-economy
- Title: 电力-经济耦合分析
- Use when: 电力经济 — 电价/电力市场、用电数据、电力与 GDP 关系、体制改革、规划预测、发电经济性、行业政策
- Don't use when: 非电力经济通用问答、双碳问题（carbon）
- Tools: `web_search` / `knowledge_retrieve` / `kg_query` / `fetch_url_content` / 记忆

## stock
- Title: 股市分析
- Use when: 个股基本面深度解读、多角色圆桌研究（基本面/短线）、量价技术面诊断
- Don't use when: 非股票通用问答、双碳（carbon）、电力经济（power-economy）；浏览器站点搜索/截图（orchestrator）
- Skills: stock-deep-analysis、stock-roundtable、stock-volume-price
- Tools: `web_search` / `knowledge_retrieve` / `kg_query` / `fetch_url_content` / 记忆
