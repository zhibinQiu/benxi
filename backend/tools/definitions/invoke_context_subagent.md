---
name: invoke_context_subagent
---
委托子 Agent 执行任务的统一入口。父智能体只编排（可见范围=本 Agent 已挂载工具/技能），子智能体才执行。

- kind=search：多源检索（文档+联网+本体+图谱）；可选 `queries` 并行关键词
- kind=use：执行已有 Skill（子层按需 `invoke_skill` / `load_uploaded_skill` / `run_skill_script`）
- kind=execute：严格按父编排的 `steps` 执行（浏览器自动化、定时通知等）；工具面=父挂载集 − 技能直执入口

## When to use
- 已知 Skill 名或用户说「请使用 xxx-skill」→ kind=use
- 浏览器操作（导航/点击/截图等）→ kind=execute + steps
- 深度多源调研 → kind=search

## When NOT to use
- 一步可完成的轻量原子工具（如单次 `web_search`、发通知）→ 父层可直接调用
- 纯常识问答 → 直接回答

## Returns
- 结构化调研/技能/编排执行结果

## Parameters

### kind (required)
子 Agent 类型：search / use / execute。

### task
任务描述（search/use 用）。最长 1200 字符。

### queries (optional)
search 可选：2–4 个关键词并行检索；不传则子 Agent 自主生成搜索词。

### steps (optional)
execute 专用：父智能体编排的步骤列表。子 Agent 严格按序执行，不自主决策。
步骤中的工具必须已挂载到当前父智能体；`invoke_skill` / `run_skill_script` 等技能直执入口会被拒绝（改用 kind=use）。
