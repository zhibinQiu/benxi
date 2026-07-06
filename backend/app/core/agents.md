# Agents 路由目录（调度层只读 · 路由决策依据）

## orchestrator
- Title: 小析
- Use when: 所有日常任务 — 联网/知识库/图谱检索、AI对话/生图/识图、图表绘制。除非下面的专精场景，否则默认走本智能体
- Don't use when: 平台文档/待办 CRUD（走 platform）、撰写正式长报告（走 report）、浏览器自动化操作（走 rpa）、定时/延迟通知（走 scheduler）、Skill 创建/修改/删除（走 skill-dev）
- Skills: web-search, knowledge-search, knowledge-research, kg-palantir, free-web-ai-chat, free-web-ai-image, free-web-ai-ask-image, mermaid-diagram
- Output: 根据任务类型直接输出结果（检索结论、AI回复、图表、综合解答等）

## platform
- Title: 平台信息
- Use when: 文档库 CRUD（搜索/创建/移动/分享/删除）、待办 CRUD、用户/部门/组织查询与管理
- Don't use when: 通用检索/问答/AI生图（由 orchestrator 直接处理）、浏览器网页操作、Skill 开发
- Skills: document-library, platform-ops, user-administration, dept-administration
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
- Skills: browser-automation
- Output: 浏览器操作结果、截图或流程信息

## scheduler
- Title: 时间调度
- Use when: 延迟/定时提醒、定时/立即通知（send_notification）、取消或列出定时任务、安排定时执行的浏览器自动化流程
- Don't use when: 立即执行的浏览器操作（走 rpa）、文档库与待办 CRUD（走 platform）、普通问答（orchestrator 直接处理）
- Skills: notification, browser-automation
- Output: 通知与定时任务创建/变更/取消结果

## skill-dev
- Title: 技能开发
- Use when: 创建/修改/删除上传型 Skill、run_skill_script 执行验证、编写网页抓取/自动化脚本包；
  创建**抓取类 Skill** 时浏览器调研页面结构作为中间步骤（调研完立即回到技能创建主流程）
- Don't use when: 纯浏览器操作无创建 Skill 意图（走 rpa）、普通问答（orchestrator 直接处理）
- Skills: skill-development（技能包管理）；浏览器调研是创建抓取类 Skill 的中间步骤，非主业
- Output: Skill 包变更或脚本执行输出
