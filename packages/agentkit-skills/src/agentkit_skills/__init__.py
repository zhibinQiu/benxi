"""agentkit-skills — Agent Skill 插件框架。"""

__version__ = "4.6.0"

from agentkit_skills.executor import (
    SkillNotFoundError,
    SkillNotReadyError,
    invoke_skill_definition,
    invoke_skill_tool,
)
from agentkit_skills.mcp_bridge import McpSkillRecord, build_mcp_skill_definition, make_mcp_tool_handler
from agentkit_skills.registry import (
    LazySkillRegistry,
    SkillRegistry,
    all_registered_skills,
    get_default_registry,
    get_skill,
    register_skill,
    set_registry_loader,
)
from agentkit_skills.routing import format_skill_route_line, truncate_route_text
from agentkit_skills.search import rank_skills_by_query, skill_query_tokens
from agentkit_skills.types import (
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
