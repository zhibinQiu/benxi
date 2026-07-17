| Tools 路由目录（调度层只读 · 简约版）

原子工具是智能体执行的最小动作单元。每个工具提供单一、可验证的操作。
工具的选择由 LLM 根据工具定义（description）和当前上下文自动决策。

## invoke_context_subagent（联网检索与深度调研统一入口）
- Use when: 所有需要联网获取信息的情况（唯一联网检索入口）；deep_research→深度调研；explore→内部多源检索
- Don't use when: 企业内部知识库检索（用 knowledge_retrieve）；用户已提供 URL（用 fetch_url_content）
- Output: 联网摘要、引用与研究结论

## knowledge_retrieve
- Use when: 检索企业文档库，按关键词匹配文档片段
- Don't use when: 需联网搜索公开信息（用 invoke_context_subagent(kind=deep_research)）、需查询实体关系图（用 kg_query）
- Output: 匹配文档标题、片段及来源

## kg_query
- Use when: 查询本体知识图谱，获取结构化实体关系
- Don't use when: 需检索文档全文（用 knowledge_retrieve）、需搜索网络（用 invoke_context_subagent(kind=deep_research)）
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
- Use when: 用户已提供 URL，需要读取页面全文
- Don't use when: 需要搜索公开信息（用 invoke_context_subagent(kind=deep_research)）
- Output: 网页正文 Markdown

## invoke_skill
- Use when: 调用已绑定的系统 Skill（文档库/技能开发/浏览器自动化等）
- Don't use when: 可直接用原子工具一步完成的任务
- Output: Skill 执行结果

## ask_user_choice
- Use when: 存在多种合理方案需要用户决定（格式选择/时间范围/风格偏好等）
- Don't use when: 已有确定答案、只需告知用户结果
- Output: 用户选择的选项

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

## invoke_context_subagent
- Use when: 所有需要联网获取信息的情况（唯一联网检索入口）；deep_research→深度联网调研；explore→内部知识多源并行检索；browser_digest→页面取证
- Don't use when: 已知 Skill 名（直接用 invoke_skill）
- Output: 结构化调研结果

## load_uploaded_skill
- Use when: 需要读取上传型 Skill 的完整 SKILL.md 内容
- Don't use when: 运行 Skill 脚本（用 run_skill_script）
- Output: SKILL.md 全文

## run_skill_script
- Use when: 执行上传型 Skill 的 main.py 入口
- Don't use when: 只需要查看 Skill 内容（用 load_uploaded_skill）
- Output: 脚本执行结论

## create_skill / update_uploaded_skill_file / delete_uploaded_skill / list_agent_skills
- Use when: 上传型 Skill 生命周期管理（创建/更新/删除/列出）
- Don't use when: 调用已有 Skill（用 invoke_skill）
- Output: 对应操作结果

## search_skills
- Use when: 按关键词搜索可用 Skill 路由
- Don't use when: 已知 Skill 名（直接用 invoke_skill）
- Output: 匹配的 Skill 列表

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
- Don't use when: 优先使用 search_skills
- Output: 工具匹配结果
