---
name: list_agent_skills
---
列出平台 Skills 目录（默认偏向上传型）。用于浏览已有 Skill，不是创建流程的一部分。

## When to use
- 「有哪些技能」「上传了哪些 Skill」
- 按关键词筛选 Skill

## When NOT to use
- 正在生成/创建 Skill 的流程中（勿用本工具代替 create_skill）
- 按任务匹配路由（优先 find_skills）

## Returns
- Skill 列表（名称、描述等）

## Parameters

### query (optional)
关键词过滤。

### limit (optional)
默认 40，最大 80。

### uploaded_only (optional)
是否仅上传型，默认 true。
