"""本体语义中枢子包 — Agent 应经 OntologyHubService 访问。

平台工厂见 ``app.services.semantic_runtime``。
"""

from .answers import (
    answer_addresses_question,
    can_answer_from_decision,
    try_direct_answer_from_decision,
)
from .intents import detect_intent_tags, tools_for_intents
from .service import OntologyHubService

__all__ = [
    "OntologyHubService",
    "answer_addresses_question",
    "can_answer_from_decision",
    "detect_intent_tags",
    "tools_for_intents",
    "try_direct_answer_from_decision",
]
