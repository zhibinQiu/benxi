"""Skill 路由 — 复杂任务先匹配已有发展技能，再考虑原子工具。"""

from __future__ import annotations

from app.agentkit.skills.routing import format_skill_route_line


# 路由描述统一维护于 app/skills/skills.md；调度层只读该文件。
# Agent 路由描述见 app/core/agents.md。
# 发展技能的路由摘要来自各 SKILL.md frontmatter，运行时合并进目录。

SKILL_DISCOVERY_RULES = """【Skill 按需发现 · 专精 Agent】
1. 业务动作经 invoke_skill(skill_name, action, params) 调用已绑定 Skill
2. 不确定用哪个 Skill 时先 find_skills(query) 发现路由，再 invoke_skill
3. 发展技能：load_uploaded_skill / run_skill_script；外部 MCP：invoke_skill(mcp-name, tool, params)
4. 复杂调研优先 search：invoke_context_subagent(kind=search, task=..., queries=[...] 可选) 委托子 Agent 多源检索
5. 路由边界见 agents.md / skills.md；选 Skill 须与专精 Agent 域一致，勿跨域混用"""

SKILL_LOADING_RULES = """【Skill 优先 · 专精 Agent · 路由基线】
1. 业务动作经 invoke_skill(skill_name, action, params) 调用已绑定 Skill
2. 发展技能：load_uploaded_skill 读 SKILL.md；可执行包用 run_skill_script
3. 外部 MCP Skill：invoke_skill(mcp-skill-name, tool, params) 调用已登记 MCP 工具
4. 简单检索用 web_search 原子工具；复杂调研深度检索用 invoke_context_subagent(kind=search)
5. skill-dev 专精：包管理直接调用 create_skill / list_agent_skills 等原子工具；
   浏览器调研（创建抓取 Skill 中间步骤）直接调用 browser_navigate 等原子工具；
   纯主题检索调研 invoke_context_subagent(kind=search, task=..., queries=[...])
6. 路由边界见 skills.md / agents.md；选 Skill 须与专精 Agent 域一致，勿跨域混用"""

SKILL_NO_LOAD_WARNING = "勿 list/load/run 已有包——直接 create_skill 生成新包"


def uploaded_skill_tag(*, has_script: bool) -> str:
    return "[脚本型]" if has_script else "[指令型]"


__all__ = [
    "SKILL_DISCOVERY_RULES",
    "SKILL_LOADING_RULES",
    "SKILL_NO_LOAD_WARNING",
    "format_skill_route_line",
    "uploaded_skill_tag",
]
