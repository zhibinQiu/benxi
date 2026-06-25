from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class AgentRuntimeStatusOut(StrEnum):
    RUNNING = "running"
    IDLE = "idle"


class AgentProfileOut(BaseModel):
    id: str
    title: str
    description: str
    enabled: bool = True
    status: AgentRuntimeStatusOut = AgentRuntimeStatusOut.IDLE
    skill_names: list[str] = Field(default_factory=list)
    default_skill_names: list[str] = Field(default_factory=list)
    skills_configurable: bool = True
    tool_categories: list[str] = Field(default_factory=list)
    tool_count: int = 0
    active_conversations: int = 0


class AgentProfileDetailOut(AgentProfileOut):
    files: list[str] = Field(default_factory=lambda: ["AGENT.md"])


class AgentProfilePatchIn(BaseModel):
    enabled: bool | None = None
    skill_names: list[str] | None = None


class AgentCatalogItemOut(BaseModel):
    """本析智能对话：用户可选专精智能体（Discovery）。"""

    id: str
    title: str
    description: str
