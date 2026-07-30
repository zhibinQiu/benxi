---
name: search_tools
---

search_tools — 按关键词搜索**原子工具**目录（内部/兼容入口）。

与 `find_skills` 的边界：
- `find_skills`：查 Skill 路由（业务能力包）
- `search_tools`：查原子工具名（执行单元）；日常优先 `find_skills` / `describe_tool`

## When to use

- 需要按关键词在原子工具目录里摸底（少见）
- 历史对话或内部链路仍指向本工具名时

## When NOT to use

- 发现/选择 Skill → 用 `find_skills`
- 已知工具名、只差参数 schema → 用 `describe_tool`
- 浏览器/已知名 Skill 执行 → `invoke_context_subagent(kind=execute|use)`

## Returns

- 匹配的原子工具摘要列表
