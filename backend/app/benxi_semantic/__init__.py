"""本析语义层：对本体（TBox）与知识图谱实例（ABox）查询/推理的统一抽象。

Agent、工具与规划侧应优先经 ``SemanticLayer`` 获取决策上下文，
避免直接拼接 Cypher 或重复实现意图检测。
"""

from __future__ import annotations

from .defaults import DEFAULT_ENTITY_TYPES, DEFAULT_RELATION_TYPES
from .intents import detect_intent_tags
from .models import AgentDecisionContext, MatchedEntity
from .query_engine import SemanticQueryEngine
from .reasoning import ReasoningEngine, ReasoningPayload
from .semantic_layer import SemanticLayer

__all__ = [
    "AgentDecisionContext",
    "DEFAULT_ENTITY_TYPES",
    "DEFAULT_RELATION_TYPES",
    "MatchedEntity",
    "ReasoningEngine",
    "ReasoningPayload",
    "SemanticLayer",
    "SemanticQueryEngine",
    "detect_intent_tags",
]

__version__ = "0.1.0"
