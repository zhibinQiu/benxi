# Skills 路由目录（调度层只读 · 简约版）

## knowledge-research
- Title: 综合调研
- Use when: 需组合图谱/联网/知识库多源取证；默认顺序图谱→联网→知识库，用户指定渠道时除外
- Don't use when: 寒暄、平台系统操作、Skill 脚本执行、附件已含完整答案
- Output: 带 [n] 引用的综合检索结论（内置编排 Skill，仅 playbook 不可 load）

## skill-development
- Title: 技能开发
- Use when: 创建/修改/删除上传型 Skill、run_skill_script 取数验证；调用方式为 invoke_skill(skill-development, call, {operation: ...})
- Don't use when: 网页/联网调研（用 invoke_context_subagent 委托 browser-automation 或 web-search 等）、平台文档操作、撰写正式长报告
- Output: Skill 包变更或脚本执行输出

## free-web-ai
- Title: 免费 AI 工具
- Use when: 需要免费 AI 对话、代码生成、文案、翻译、生图（文字描述）、识图问答等任务，无需付费 API key
- Don't use when: 企业内部知识库检索（用 knowledge-search）、平台 CRUD、需联网获取最新信息（用 web-search）、精确构图或高分辨率出图（推荐专业工具）、纯 OCR 提取（用 ocr feature）
- Output: AI 文本回复 / 图片 / 图片内容描述