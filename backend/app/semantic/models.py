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
    props: dict[str, Any] = field(default_factory=dict)


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
class ResolvedConcept:
    """自然语言映射到的本体概念（Class / 相关属性与关系）。"""

    type_code: str
    label: str = ""
    property_keys: list[str] = field(default_factory=list)
    relation_codes: list[str] = field(default_factory=list)
    aliases_hit: list[str] = field(default_factory=list)
    confidence: float = 0.0
    rationale: str = ""


@dataclass(slots=True)
class FieldBinding:
    """业务概念属性 → 事实数据源字段绑定。"""

    concept: str
    property_key: str
    source: str  # neo4j | sql | document
    neo4j_prop: str = ""
    table: str = ""
    column: str = ""
    join_template: str = ""  # 受控联查模板 id（注册制）
    notes: str = ""


@dataclass(slots=True)
class Neo4jPlanStep:
    """参数化 Cypher 步骤（由本体规划，由 KG 服务执行）。"""

    description: str
    cypher: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SqlPlanStep:
    """参数化受控 SQL 步骤（由本体规划，由 SqlExecutor 只读执行）。"""

    description: str
    sql: str
    params: dict[str, Any] = field(default_factory=dict)
    table: str = ""
    columns: list[str] = field(default_factory=list)
    join_template: str = ""


@dataclass(slots=True)
class QueryPlan:
    """语义中枢产出的查询计划：问什么、查什么、去哪查、按何路径、为何。"""

    question: str = ""
    intent_tags: list[str] = field(default_factory=list)
    concepts: list[ResolvedConcept] = field(default_factory=list)
    field_bindings: list[FieldBinding] = field(default_factory=list)
    neo4j_steps: list[Neo4jPlanStep] = field(default_factory=list)
    sql_steps: list[SqlPlanStep] = field(default_factory=list)
    preferred_tools: list[str] = field(default_factory=list)
    blocked_tools: list[str] = field(default_factory=list)
    why: str = ""
    matched_entity_ids: list[str] = field(default_factory=list)

    def summary_text(self, *, max_chars: int = 1200) -> str:
        parts: list[str] = []
        if self.why:
            parts.append(f"决策说明: {self.why}")
        if self.intent_tags:
            parts.append(f"意图: {', '.join(self.intent_tags)}")
        if self.concepts:
            labels = [
                f"{c.label or c.type_code}({c.type_code})" for c in self.concepts[:8]
            ]
            parts.append(f"概念: {', '.join(labels)}")
        if self.field_bindings:
            binds = [
                f"{b.concept}.{b.property_key}→{b.source}"
                for b in self.field_bindings[:8]
            ]
            parts.append(f"字段映射: {', '.join(binds)}")
        if self.neo4j_steps:
            parts.append(
                "Neo4j路径: " + " → ".join(s.description for s in self.neo4j_steps[:6])
            )
        if self.sql_steps:
            parts.append(
                "SQL路径: " + " → ".join(s.description for s in self.sql_steps[:6])
            )
        if self.preferred_tools:
            parts.append(f"优先工具: {', '.join(self.preferred_tools)}")
        text = "\n".join(parts).strip()
        return text[:max_chars] if text else ""


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
    query_plan: QueryPlan | None = None
    evidence_paths: list[str] = field(default_factory=list)

    def planning_text(self, *, max_chars: int = 1800) -> str:
        """供规划器注入的紧凑文本。"""
        parts: list[str] = []
        if self.query_plan and self.query_plan.why:
            parts.append(f"问什么/为何: {self.query_plan.why}")
        if self.intent_tags:
            parts.append(f"意图标签: {', '.join(self.intent_tags)}")
        if self.preferred_tools:
            parts.append(f"优先工具: {', '.join(self.preferred_tools)}")
        if self.blocked_tools:
            parts.append(f"避免工具: {', '.join(self.blocked_tools)}")
        if self.capability_hints:
            parts.append(f"能力线索: {', '.join(self.capability_hints)}")
        if self.evidence_paths:
            path_lines = ["【多跳证据路径】"]
            for i, p in enumerate(self.evidence_paths[:8], 1):
                path_lines.append(f"路径{i}: {p}")
            parts.append("\n".join(path_lines))
        if self.query_plan:
            plan_sum = self.query_plan.summary_text(max_chars=600)
            if plan_sum and plan_sum not in "\n".join(parts):
                parts.append(plan_sum)
        if self.tbox_compact:
            parts.append(self.tbox_compact)
        if self.abox_snippets:
            # 路径已单独前置，避免重复占满预算
            snip = self.abox_snippets
            if self.evidence_paths and snip.startswith("【多跳证据路径】"):
                marker = "【知识图谱推理上下文】"
                idx = snip.find(marker)
                if idx >= 0:
                    snip = snip[idx:]
            parts.append(snip)
        text = "\n".join(p for p in parts if p).strip()
        return text[:max_chars] if text else ""
