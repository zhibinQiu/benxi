# Skills 路由目录（调度层只读 · 简约版）

## web-search
- Title: 联网搜索
- Use when: 最新政策/行情/新闻/价格或需联网检索公开信息
- Don't use when: 企业内部知识库检索（用 knowledge-search）、平台系统操作、撰写长报告
- Output: 联网摘要与引用

## knowledge-search
- Title: 知识库检索
- Use when: 从企业知识库检索制度、文档片段或内部资料
- Don't use when: 最新公开资讯（用 web-search）、平台文档 CRUD（用 document-library）、撰写长报告
- Output: 文档片段与 [n] 引用

## kg-palantir
- Title: 本体图谱
- Use when: 实体关联、产业链、组织关系或本体图谱概念查询；部门成员关系查询
- Don't use when: 最新新闻、平台用户/部门 CRUD、撰写长报告
- Output: 图谱实体与关系上下文

## knowledge-research
- Title: 综合调研
- Use when: 需组合图谱/联网/知识库多源取证；默认顺序图谱→联网→知识库，用户指定渠道时除外
- Don't use when: 寒暄、平台系统操作、Skill 脚本执行、附件已含完整答案
- Output: 带 [n] 引用的综合检索结论（内置编排 Skill，仅 playbook 不可 load）

## document-library
- Title: 文档库
- Use when: 搜索/读取/创建/移动/分享/删除文档或文件夹
- Don't use when: 仅需知识库片段检索（用 knowledge-search）、联网调研、撰写长报告
- Output: 操作结果与结构化 data

## platform-ops
- Title: 平台待办
- Use when: 待办 CRUD（list_todos, create_todo, update_todo, delete_todo）
- Don't use when: 文档库操作（用 document-library）、通知/定时提醒（用 notification）、知识检索、浏览器自动化
- Output: 待办操作结果

## notification
- Title: 系统通知
- Use when: 即时通知（send_notification）、定时提醒（schedule_notification）、查看/取消定时通知
- Don't use when: 待办 CRUD（用 platform-ops）、文档库操作、知识检索、浏览器自动化
- Output: 通知/定时任务操作结果

## browser-automation
- Title: 浏览器自动化
- Use when: 网页导航/站点搜索/填表/点击/截图、录制或回放浏览器流程；skill-dev 创建抓取类 Skill 时调研页面结构作为**中间步骤**
- Don't use when: 纯主题调研无浏览器操作意图（用 web-search）、平台文档/待办、撰写长报告、定时安排（用 scheduler）
- Output: 浏览器操作结果或截图路径

## user-administration
- Title: 用户管理
- Use when: 查询或管理系统用户、成员列表、账号 CRUD（须 admin.user 权限）
- Don't use when: 部门架构 CRUD（用 dept-administration）、知识检索
- Output: 用户列表或 CRUD 结果

## dept-administration
- Title: 部门管理
- Use when: 查询或管理组织架构、部门树、部门 CRUD（须 admin.dept 权限）
- Don't use when: 用户账号 CRUD（用 user-administration）、知识检索
- Output: 部门列表或 CRUD 结果

## mermaid-diagram
- Title: Mermaid 图表绘制
- Use when: 用户要求绘制流程图/思维导图/架构图/时序图/关系图等可视化图表，单次一张主图
- Don't use when: 撰写长篇报告正文（用 report）、知识检索调研、浏览器操作、平台信息查询、Skill 开发
- Output: ```mermaid 围栏源码

## skill-development
- Title: 技能开发
- Use when: 创建/修改/删除上传型 Skill、run_skill_script 取数验证；调用方式为 invoke_skill(skill-development, call, {operation: ...})
- Don't use when: 网页/联网调研（用 invoke_context_subagent 委托 browser-automation 或 web-search 等）、平台文档操作、撰写正式长报告
- Output: Skill 包变更或脚本执行输出

## free-web-ai-chat
- Title: 免费 AI 对话
- Use when: 免费 AI 文本对话、代码生成、文案、翻译等文本任务，无需付费 API key 即可使用网页版大模型
- Don't use when: 企业内部知识库检索（用 knowledge-search）、平台 CRUD、需联网获取最新信息（用 web-search）
- Output: AI 文本回复

## free-web-ai-image
- Title: 免费 AI 生图
- Use when: 用文字描述生成图片（支持豆包/千问），无需付费 API key
- Don't use when: 需要精确构图或高分辨率出图（推荐用专业生图工具）、纯文本对话
- Output: 图片描述文本

## free-web-ai-ask-image
- Title: 免费 AI 识图问答
- Use when: 上传图片并询问图片内容、识别图片中的文字/物体/场景
- Don't use when: 纯文本对话（用 free-web-ai-chat）、OCR 提取（用 ocr feature）
- Output: 图片内容描述/回答