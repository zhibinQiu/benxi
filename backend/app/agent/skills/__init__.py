"""app.agent.skills — Agent Skill 插件框架。"""

from app.agent import __version__  # noqa: F401

from app.agent.skills.executor import (
    SkillNotFoundError,
    SkillNotReadyError,
    invoke_skill_definition,
    invoke_skill_tool,
)
from app.agent.skills.mcp_bridge import McpSkillRecord, build_mcp_skill_definition, make_mcp_tool_handler
from app.agent.skills.registry import (
    LazySkillRegistry,
    SkillRegistry,
    all_registered_skills,
    get_default_registry,
    get_skill,
    register_skill,
    set_registry_loader,
)
from app.agent.skills.routing import format_skill_route_line, truncate_route_text
from app.agent.skills.search import rank_skills_by_query, skill_query_tokens
from app.agent.skills.types import (
    SkillDefinition,
    SkillHandler,
    SkillInvocationContext,
    SkillInvocationResult,
    SkillKind,
    SkillReadiness,
    SkillSource,
    SkillToolSpec,
)

__all__ = [
    "LazySkillRegistry",
    "McpSkillRecord",
    "SkillDefinition",
    "SkillHandler",
    "SkillInvocationContext",
    "SkillInvocationResult",
    "SkillKind",
    "SkillNotFoundError",
    "SkillNotReadyError",
    "SkillReadiness",
    "SkillRegistry",
    "SkillSource",
    "SkillToolSpec",
    "all_registered_skills",
    "build_mcp_skill_definition",
    "format_skill_route_line",
    "get_default_registry",
    "get_skill",
    "invoke_skill_definition",
    "invoke_skill_tool",
    "make_mcp_tool_handler",
    "rank_skills_by_query",
    "register_skill",
    "set_registry_loader",
    "skill_query_tokens",
    "truncate_route_text",
]
