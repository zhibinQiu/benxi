"""可抽离库：语义决策（``app.semantic``）。

职责：意图/概念解析、字段绑定、受控 SQL/Cypher 规划、图谱直答判定。
禁止依赖：``app.services`` / ``app.core`` 连接工厂；Neo4j driver 与本体只读端口由宿主注入。
平台组装入口：``app.services.semantic_runtime``。

与 ``app.ontology``（TBox RDF/SHACL 持久化）职责不同：本包做决策，不直连 GraphDB。
"""

from __future__ import annotations

from .defaults import DEFAULT_ENTITY_TYPES, DEFAULT_RELATION_TYPES
from .kg import (
    KgQueryService,
    ReasoningEngine,
    ReasoningPayload,
    SemanticQueryEngine,
    question_match_tokens,
)
from .models import (
    AgentDecisionContext,
    FieldBinding,
    MatchedEntity,
    Neo4jPlanStep,
    QueryPlan,
    ResolvedConcept,
    SqlPlanStep,
)
from .ontology import (
    OntologyHubService,
    can_answer_from_decision,
    detect_intent_tags,
    try_direct_answer_from_decision,
)

__all__ = [
    "AgentDecisionContext",
    "DEFAULT_ENTITY_TYPES",
    "DEFAULT_RELATION_TYPES",
    "FieldBinding",
    "KgQueryService",
    "MatchedEntity",
    "Neo4jPlanStep",
    "OntologyHubService",
    "QueryPlan",
    "ReasoningEngine",
    "ReasoningPayload",
    "ResolvedConcept",
    "SemanticQueryEngine",
    "SqlPlanStep",
    "can_answer_from_decision",
    "detect_intent_tags",
    "question_match_tokens",
    "try_direct_answer_from_decision",
]

__version__ = "0.2.0"
