| Tools 路由目录（调度层只读 · 简约版）

原子工具是智能体执行的最小动作单元。每个工具提供单一、可验证的操作。
工具的选择由 LLM 根据工具定义（description）和当前上下文自动决策。

## invoke_context_subagent（子智能体统一入口）
- Use when: 所有需要子智能体自主执行的场景
  - kind=search：深度联网检索（搜索+知识库+本体+图谱，多源交叉验证）
  - kind=use：执行已有 Skill
  - kind=execute：严格按编排步骤执行（浏览器自动化等具体操作），也可用于父智能体透明委托
- Don't use when: 可直接用原子工具一步完成的任务、已确定的问题（直接回答）
- Output: 子智能体执行结果

## knowledge_retrieve
- Use when: 检索企业文档库，按关键词匹配文档片段
- Don't use when: 需联网搜索公开信息（用 invoke_context_subagent(kind=search)）、需查询实体关系图（用 kg_query）
- Output: 匹配文档标题、片段及来源

## kg_query
- Use when: 查询本体知识图谱，获取结构化实体关系
- Don't use when: 需检索文档全文（用 knowledge_retrieve）、需搜索网络（用 invoke_context_subagent(kind=search)）
- Output: 匹配实体、关系及属性

## send_notification
- Use when: 用户要求立即发送站内通知
- Don't use when: 定时发送（用 schedule_notification）、发送外部消息（不支持）
- Output: 通知 ID 和发送结果

## schedule_notification
- Use when: 用户说「X秒/分钟后提醒我」「定时通知我」「设置提醒」
- Don't use when: 需要立即发送（用 send_notification）、发送外部消息（不支持）、周期重复提醒（不支持）
- Output: 定时通知 ID 和计划发送时间

## list_scheduled_notifications
- Use when: 用户查看有哪些待发送的定时通知
- Don't use when: 查看已发送或已取消的通知（不可见）
- Output: 待发送通知列表

## cancel_scheduled_notification
- Use when: 用户要求取消尚未发送的定时通知
- Don't use when: 通知已发送（无法取消）
- Output: 取消结果

## fetch_url_content
- Use when: 用户已提供 URL，需要读取页面全文；或 web_search 摘要不够用，择需读全文
- Don't use when: 需要搜索公开信息（用 invoke_context_subagent(kind=search)）
- Output: 网页正文 Markdown

## invoke_skill
- Use when: **use 子层或 skill-dev 专精**调用已绑定 Skill
- Don't use when: 父编排层默认路径（父层用 `invoke_context_subagent(kind=use)`）；可直接用原子工具一步完成的任务
- Output: Skill 执行结果

## ask_user_choice
- Use when: 存在多种合理方案需要用户决定（格式选择/时间范围/风格偏好等）
- Don't use when: 已有确定答案、只需告知用户结果
- Output: 用户选择的选项

## f10_data
- Use when: 需要对个股进行深度基本面分析时，一键获取公司概况、主营构成（分产品营收/毛利率）、财务摘要、盈利指标（ROE/毛利率/净利率）、区间行情与涨跌幅、主力资金流向、业绩预告、股东户数、北向资金持仓、近期公告、互动易问答。
- Don't use when: 仅需实时行情（用 stock_quote）、仅需 K 线（用 stock_kline）、仅需搜索股票代码（用 finance_search）
- Output: 包含 12 个维度数据的结构化报告，以及 Markdown 摘要

## carbon_price
- Use when: 查询全国 CEA / CCER / 地方试点碳价行情，需要官方源摘要
- Don't use when: 每日碳新闻资讯（用 invoke_context_subagent kind=execute 浏览器查最新）、政策原文（用 carbon_policy）
- Output: 多源碳价摘要 Markdown，附 URL 与查询时间

## carbon_policy
- Use when: 查询双碳政策法规（gov/ndrc/mee/miit 等官方源摘要）
- Don't use when: 媒体新闻解读/每日资讯（用浏览器）、实时碳价（用 carbon_price）
- Output: 多源政策摘要 Markdown，附 URL 与查询时间

## carbon_data
- Use when: 查询排放数据 / CCER / 国际碳市场 / 地方双碳方案（topic=emission|ccer|international|local）
- Don't use when: 碳价（用 carbon_price）、政策法规（用 carbon_policy）、新闻资讯（用浏览器）
- Output: 多源结构化数据摘要 Markdown，附 URL 与查询时间

## request_orchestrator_assist
- Use when: 专精 Agent 遇到本域无法完成的任务，需要调度层协调其他专精协助
- Don't use when: 可直接用已有工具完成
- Output: 调度协助结果

## read_agent_memory
- Use when: 需要读取用户的个性化配置或长期记忆
- Don't use when: 查询平台数据
- Output: 用户 MEMORY.md 内容

## append_agent_memory
- Use when: 用户要求记住某个偏好或信息供后续使用
- Don't use when: 一次性临时信息
- Output: 记忆已保存

## load_uploaded_skill
- Use when: use 子层或 skill-dev 读取上传型 Skill 的 SKILL.md
- Don't use when: 父编排层直调；运行脚本（用 run_skill_script）
- Output: SKILL.md 全文

## run_skill_script
- Use when: use 子层或 skill-dev 执行上传型 Skill 的 main.py
- Don't use when: 父编排层直调；只查看内容（用 load_uploaded_skill）
- Output: 脚本执行结论

## create_skill / update_uploaded_skill_file / delete_uploaded_skill / list_agent_skills
- Use when: skill-dev 专精管理上传型 Skill 生命周期
- Don't use when: 父编排层；调用已有 Skill（父层 kind=use / 子层 invoke_skill）
- Output: 对应操作结果

## find_skills
- Use when: 在**当前 Agent 已挂载** Skill 范围内按关键词查找路由（父编排发现入口）
- Don't use when: 已知 Skill 名（父层 `kind=use`）；查未挂载 Skill；查原子工具（`describe_tool` / `search_tools`）
- Output: 匹配的已挂载 Skill 列表

## run_tool_batch
- Use when: 批量执行多个只读/检索工具
- Don't use when: 有写操作或需要逐步决策的复杂任务
- Output: 各工具执行结果

## list_todos / create_todo / update_todo / delete_todo
- Use when: 待办事项 CRUD 操作
- Don't use when: 系统通知（用 send_notification）
- Output: 待办操作结果

## search_documents_by_name / read_document_content / list_library_documents / list_manageable_documents / list_document_folders / create_kb_folder / create_library_document / rename_document / move_document / share_document / delete_document / update_kb_folder / delete_kb_folder / sync_document_knowledge / reindex_document
- Use when: 文档库 CRUD 操作
- Don't use when: 通用知识库检索（用 knowledge_retrieve）
- Output: 文档库操作结果

## browser_navigate / browser_snapshot / browser_click / browser_type / browser_fill / browser_screenshot / browser_save_workflow / browser_close_session / browser_replay_workflow / browser_run_task / schedule_browser_workflow
- Use when: 浏览器自动化操作（导航/点击/填表/截图/录制/回放）
- Don't use when: 普通数据查询（用知识库检索工具）
- Output: 浏览器操作结果

## list_users / create_user / update_user / delete_user / list_departments / create_department / update_department / delete_department
- Use when: 用户与部门管理（需管理员权限）
- Don't use when: 非管理场景
- Output: 用户/部门操作结果

## search_tools
- Use when: 内部搜索原子工具（内部使用）
- Don't use when: 优先使用 find_skills
- Output: 工具匹配结果
