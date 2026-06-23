"""Agent Skills 框架 — 内置平台能力与上传包统一注册、发现与执行。"""

from app.skills.catalog import (
    build_agent_catalog_prompt,
    get_merged_skill_definition,
    list_all_skill_definitions,
    set_builtin_binding,
)
from app.skills.executor import invoke_skill_tool
from app.skills.registry import ensure_skills_loaded, get_skill
from app.skills.types import (
    SkillDefinition,
    SkillInvocationContext,
    SkillInvocationResult,
    SkillReadiness,
    SkillSource,
)

__all__ = [
    "SkillDefinition",
    "SkillInvocationContext",
    "SkillInvocationResult",
    "SkillReadiness",
    "SkillSource",
    "build_agent_catalog_prompt",
    "ensure_skills_loaded",
    "get_merged_skill_definition",
    "get_skill",
    "invoke_skill_tool",
    "list_all_skill_definitions",
    "set_builtin_binding",
]
