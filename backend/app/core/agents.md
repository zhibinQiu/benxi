# Agents 路由目录（调度层只读 · 路由决策依据）

## orchestrator
- Title: 小析
- Use when: 所有日常任务 — 检索、查询、图表绘制、AI对话/生图/识图等。父层编排：仅见**已挂载**工具与技能；执行交给子智能体或路由专精 Agent
- Don't use when: 平台文档/待办/通知/用户部门 CRUD（走 platform）、撰写正式长报告（走 report）、Skill 创建/修改/删除（走 skill-dev）、双碳专业分析（走 carbon）、电力经济分析（走 power-economy）、股市深度分析（走 stock）
- Skills: 仅已挂载（find_skills）；不可直执 invoke_skill/run_skill_script；执行用 `invoke_context_subagent(kind=use)`
- Tools: 仅已挂载原子工具（默认含检索/通知/browser_* 等，以 binding 为准）；父层可直调编排/发现原语；其余调用运行时透明委托 kind=execute

## platform
- Title: 平台操作
- Use when: 文档库 CRUD（搜索/创建/移动/分享/删除）、待办 CRUD、系统通知（发送/定时/取消）、用户/部门/组织查询与管理
- Don't use when: 通用检索/问答/AI生图（由 orchestrator 处理）、浏览器网页操作、Skill 开发
- Tools: 文档库/待办/通知/用户部门管理/记忆等原子工具

## report
- Title: 撰写报告
- Use when: 撰写/扩写/生成可研、方案、计划书、调研/测试/工作类长文档
- Don't use when: 简单短问答、平台信息操作、图表绘制
- Skills: report-*（发展 Skill 白名单，动态挂载）
- Tools: `web_search` / `knowledge_retrieve` / `fetch_url_content` / 记忆

## skill-dev
- Title: 技能开发
- Use when: 创建/修改/删除上传型 Skill、run_skill_script 执行验证、编写网页抓取/自动化脚本包；
  创建**抓取类 Skill** 时浏览器调研页面结构作为中间步骤（调研完立即回到技能创建主流程）
- Don't use when: 纯浏览器操作（orchestrator 委托 execute 子智能体）、普通问答（orchestrator 处理）
- Skills: skill-development（技能包管理，动态挂载）
- Tools: Skill 管理 / 浏览器 / `web_search` / `knowledge_retrieve` / 记忆

## carbon
- Title: 双碳智能体
- Use when: 双碳领域相关问题：碳市场行情、碳交易规则、碳中和/碳达峰政策、CCER、碳排放核算、双碳政策解读与新闻分析等
- Don't use when: 其他非双碳领域问题
- Skills: carbon-qa（双碳问答；ask 编排 carbon_price/carbon_policy/carbon_data；新闻走浏览器 kind=execute）
- Tools: carbon_price / carbon_policy / carbon_data
- Tools: `web_search` / `knowledge_retrieve` / `kg_query` / `fetch_url_content` / 记忆

## power-economy
- Title: 电力-经济耦合分析
- Use when: 电力经济领域问题：电力市场行情/电价查询、用电数据分析、电力-经济关系分析（电力消费弹性系数/GDP与用电量关系）、电力体制改革、电力规划预测、发电经济性、电力行业政策解读等
- Don't use when: 非电力经济领域的通用问答、双碳领域问题（走 carbon）
- Tools: `web_search` / `knowledge_retrieve` / `kg_query` / `fetch_url_content` / 记忆

## stock
- Title: 股市分析
- Use when: 个股基本面深度解读（财务/估值/行业格局）、多角色圆桌对抗性研究（含基本面与短线两个研究方向）、量价技术面诊断与买卖决策参考
- Don't use when: 非股票领域的通用问答、双碳领域问题（走 carbon）、电力经济分析（走 power-economy）
- Skills: stock-deep-analysis（AI 深度解读）、stock-roundtable（圆桌会议）、stock-volume-price（量价会诊）
- Tools: `web_search` / `knowledge_retrieve` / `kg_query` / `fetch_url_content` / 记忆
