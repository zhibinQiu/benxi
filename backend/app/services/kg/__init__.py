"""知识图谱服务包 — 按职责拆分，kg_service 保留对外兼容门面。

模块：
- entity_commands: 实体批量删除、清空图谱
- extraction_targets: 批量抽离目标收集（权限与范围）
"""

from app.services.kg.entity_commands import batch_delete_entities, clear_user_graph
from app.services.kg.extraction_targets import (
    SCOPE_KNOWLEDGE,
    SCOPE_PLATFORM,
    ExtractionTargetPlan,
    collect_extraction_targets,
)

__all__ = [
    "SCOPE_KNOWLEDGE",
    "SCOPE_PLATFORM",
    "ExtractionTargetPlan",
    "batch_delete_entities",
    "clear_user_graph",
    "collect_extraction_targets",
]
