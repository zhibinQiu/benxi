# Changelog

## 4.6.0 (2026-07-06)

- 版本统一至 4.6.0（与 doc-platform 对齐）
- 新增 `__init__.py` 中 `__version__` 暴露
- 完善 README：设计原则、注册与调用示例、MCP 集成说明
- 新增 `mcp_bridge.py` MCP Skill 桥接
- 新增 `search.py` 关键词搜索与排名
- 新增 `routing.py` 路由文案格式化

## 0.2.0 (2024-07-06)

- 统一子包版本至 0.2.0
- 添加 `project.urls`、LICENSE、py.typed
- 完善 PyPI classifiers

## 0.1.0 (2024-06-01)

- 初始版本
- Skill 核心类型（SkillDefinition、SkillToolSpec、SkillHandler 等）
- Skill 注册表（SkillRegistry、LazySkillRegistry）
- 工具执行器（invoke_skill_definition、invoke_skill_tool）
- MCP Skill 桥接（build_mcp_skill_definition、make_mcp_tool_handler）
- 关键词搜索与排名（rank_skills_by_query、skill_query_tokens）
- 路由文案格式化（format_skill_route_line）
