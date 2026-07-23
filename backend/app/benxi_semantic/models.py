"""语义层结构化模型（与 FastAPI schema 解耦）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MatchedEntity:
    """问题文本中命中的图谱实体。"""

    id: str
    name: str
    type_code: str
    score: float = 0.0
    description: str = ""


@dataclass(slots=True)
class NeighborHit:
    """邻居节点。"""

    id: str
    name: str
    type_code: str
    relation_type: str
    distance: int = 1
    direction: str = "out"  # out | in | undirected


@dataclass(slots=True)
class PathHop:
    """路径中的一跳。"""

    entity_id: str
    entity_name: str
    type_code: str = ""
    relation_type: str = ""


@dataclass(slots=True)
class PathResult:
    """两端实体之间的一条路径。"""

    hops: list[PathHop] = field(default_factory=list)
    length: int = 0


@dataclass(slots=True)
class GraphStats:
    """图谱统计。"""

    total_entities: int = 0
    total_relations: int = 0
    entity_type_counts: dict[str, int] = field(default_factory=dict)
    relation_type_counts: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class AgentDecisionContext:
    """面向 Agent 规划/工具选型的结构化语义决策上下文。"""

    matched_entities: list[MatchedEntity] = field(default_factory=list)
    abox_snippets: str = ""
    tbox_compact: str = ""
    intent_tags: list[str] = field(default_factory=list)
    preferred_tools: list[str] = field(default_factory=list)
    blocked_tools: list[str] = field(default_factory=list)
    confidence: float = 0.0
    has_material: bool = False
    citations: list[dict[str, Any]] = field(default_factory=list)
    entity_count: int = 0
    relation_count: int = 0
    reasoning_hops: int = 0
    inferred_entities: int = 0
    capability_hints: list[str] = field(default_factory=list)

    def planning_text(self, *, max_chars: int = 1800) -> str:
        """供规划器注入的紧凑文本。"""
        parts: list[str] = []
        if self.intent_tags:
            parts.append(f"意图标签: {', '.join(self.intent_tags)}")
        if self.preferred_tools:
            parts.append(f"优先工具: {', '.join(self.preferred_tools)}")
        if self.blocked_tools:
            parts.append(f"避免工具: {', '.join(self.blocked_tools)}")
        if self.capability_hints:
            parts.append(f"能力线索: {'; '.join(self.capability_hints)}")
        if self.tbox_compact:
            parts.append(self.tbox_compact)
        if self.abox_snippets:
            parts.append(self.abox_snippets)
        text = "\n".join(p for p in parts if p).strip()
        return text[:max_chars] if text else ""
