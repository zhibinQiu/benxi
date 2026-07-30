---
name: find_skills
---

find_skills — 在**当前智能体已挂载**的 Skill 范围内按关键词查找路由（父编排可直调）。

不是平台全库搜索。未挂载到本 Agent 的 Skill 不会出现在结果中。

## When to use

- 不确定该用哪个**已挂载** Skill，需要按意图发现路由
- 用户提到某类能力且可能对应已挂载 Skill

## When NOT to use

- 已知确切 Skill 名 → 父层委托 `invoke_context_subagent(kind=use)`
- 浏览器导航/截图等 → `kind=execute` 或调已挂载 browser_*（运行时透明委托）
- 查找原子工具名/参数 → 用 `describe_tool` / `search_tools`（同样限于已挂载工具）

## Returns

- 匹配的已挂载 Skill 路由列表（名称与简述）
