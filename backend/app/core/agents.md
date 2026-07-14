# Agents 路由目录（调度层只读 · 路由决策依据）

## orchestrator
- Title: 小析
- Use when: 所有日常任务 — 联网检索、知识库检索、本体图谱查询、AI对话/生图/识图、图表绘制（流程图/思维导图/架构图/时序图/关系图等）、双碳问答。除非下面的专精场景，否则默认走本智能体
- Don't use when: 平台文档/待办/通知/用户部门 CRUD（走 platform）、撰写正式长报告（走 report）、浏览器自动化操作（走 rpa）、Skill 创建/修改/删除（走 skill-dev）
- Skills: 无（通过原子工具直接执行：web_search, knowledge_retrieve, kg_query, mermaid_diagram, read_agent_memory 等）
- Output: 根据任务类型直接输出结果（检索结论、AI回复、图表、综合解答等）

## platform
- Title: 平台操作
- Use when: 文档库 CRUD（搜索/创建/移动/分享/删除）、待办 CRUD、系统通知（发送/定时/取消）、用户/部门/组织查询与管理
- Don't use when: 通用检索/问答/AI生图（由 orchestrator 直接处理）、浏览器网页操作、Skill 开发
- Skills: 无（通过原子工具直接执行：search_documents_by_name, create_library_document, list_todos, create_todo, send_notification, schedule_notification, list_users 等）
- Output: 平台操作结果与结构化数据摘要

## report
- Title: 撰写报告
- Use when: 撰写/扩写/生成可研、方案、计划书、调研/测试/工作类长文档
- Don't use when: 简单短问答、平台信息操作、图表绘制（orchestrator 可直出）
- Skills: report-*（发展 Skill 白名单）
- Output: 结构化长报告正文

## rpa
- Title: 浏览器自动化
- Use when: 指定网站导航/搜索/填表/点击/截图、录制或回放浏览器流程；用户明确要求「打开网页」「截图」「点击某元素」「填表」等浏览器交互操作
- Don't use when: 纯主题调研（orchestrator 可直接搜索）、平台内文档/待办、定时安排
- Skills: 无（通过原子工具直接执行：browser_navigate, browser_click, browser_screenshot 等）
- Output: 浏览器操作结果、截图或流程信息

## skill-dev
- Title: 技能开发
- Use when: 创建/修改/删除上传型 Skill、run_skill_script 执行验证、编写网页抓取/自动化脚本包；
  创建**抓取类 Skill** 时浏览器调研页面结构作为中间步骤（调研完立即回到技能创建主流程）
- Don't use when: 纯浏览器操作无创建 Skill 意图（走 rpa）、普通问答（orchestrator 直接处理）
- Skills: skill-development（技能包管理）；浏览器调研是创建抓取类 Skill 的中间步骤，非主业
- Output: Skill 包变更或脚本执行输出

## carbon
- Title: 双碳智能体
- Use when: 双碳领域相关问题：碳市场行情、碳交易规则、碳中和/碳达峰政策、CCER、碳排放核算、双碳政策解读与新闻分析等
- Don't use when: 其他非双碳领域问题
- Skills: 无（通过原子工具直接执行：carbon_qa_query, web_search, knowledge_retrieve, kg_query 等）
- Output: 双碳领域专业分析结果与建议

## power-economy
- Title: 电力-经济耦合分析
- Use when: 电力经济领域问题：电力市场行情/电价查询、用电数据分析、电力-经济关系分析（电力消费弹性系数/GDP与用电量关系）、电力体制改革、电力规划预测、发电经济性、电力行业政策解读等
- Don't use when: 非电力经济领域的通用问答、双碳领域问题（走 carbon）
- Skills: 无（通过原子工具直接执行：web_search, knowledge_retrieve, kg_query 等）
- Output: 电力经济领域专业分析结果与建议
