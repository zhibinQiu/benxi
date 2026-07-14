"""Skill 路由 — 复杂任务先匹配已有发展技能，再考虑原子工具。"""

from __future__ import annotations

from app.agentkit.skills.routing import format_skill_route_line


# 路由描述统一维护于 app/skills/skills.md；调度层只读该文件。
# Agent 路由描述见 app/core/agents.md。
# 发展技能的路由摘要来自各 SKILL.md frontmatter，运行时合并进目录。

SKILL_DISCOVERY_RULES = """【Skill 按需发现 · 专精 Agent】
1. 业务动作经 invoke_skill(skill_name, action, params) 调用已绑定 Skill
2. 不确定用哪个 Skill 时先 search_skills(query) 发现路由，再 invoke_skill
3. 发展技能：load_uploaded_skill / run_skill_script；外部 MCP：invoke_skill(mcp-name, tool, params)
4. explore 多 query：invoke_context_subagent(kind=explore, queries=[...]) 并行检索；单 query 可只传 task
5. 内置编排 Skill（knowledge-research）仅 playbook，勿 load
6. 路由边界见 agents.md / skills.md；选 Skill 须与专精 Agent 域一致，勿跨域混用"""

SKILL_LOADING_RULES = """【Skill 优先 · 专精 Agent · 路由基线】
1. 业务动作经 invoke_skill(skill_name, action, params) 调用已绑定 Skill
2. 发展技能：load_uploaded_skill 读 SKILL.md；可执行包用 run_skill_script
3. 外部 MCP Skill：invoke_skill(mcp-skill-name, tool, params) 调用已登记 MCP 工具
4. 检索：invoke_skill(web-search, search, {query})；文档库：invoke_skill(document-library, call, {operation, params})
5. skill-dev 专精：包管理 invoke_skill(skill-development, call, {operation, params})；
   浏览器调研（创建抓取 Skill 中间步骤）直接 invoke_skill(browser-automation, call, ...)；
   纯主题检索调研 invoke_context_subagent(kind=explore, queries=[...])
6. 内置编排 Skill（knowledge-research）仅 playbook，勿 load
7. 路由边界见 skills.md / agents.md；选 Skill 须与专精 Agent 域一致，勿跨域混用"""


def uploaded_skill_tag(*, has_script: bool) -> str:
    return "[脚本型]" if has_script else "[指令型]"


__all__ = [
    "SKILL_DISCOVERY_RULES",
    "SKILL_LOADING_RULES",
    "format_skill_route_line",
    "uploaded_skill_tag",
]
