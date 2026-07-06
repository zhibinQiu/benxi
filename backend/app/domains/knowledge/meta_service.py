"""知识库 API 探活与 /knowledge/meta 载荷。

``build_rag_meta_payload`` 供前端判断 KnowFlow 是否可用、展示 ui_hint；
实现上统一经 ``knowledge.client_probe`` / ``knowledge.stack_reachable``，
不在此重复 ``get_settings().knowflow_enabled and ...`` 组合判断。
"""

from __future__ import annotations

from app.config import get_settings
from app.core.user_messages import KNOWLEDGE_NOT_ENABLED, KNOWLEDGE_SERVICE_UNAVAILABLE
from app.domains.knowledge import knowledge
from app.services.ragflow_naming import dataset_display_label_personal
from app.services.ragflow_scope_service import (
    dept_suffix_labels_for_theme,
    knowflow_kb_labels_for_user,
)


def build_rag_meta_payload(db, user) -> dict:
    """供前端判断 KnowFlow/RAGFlow API 是否可用。

    实现思路：
    1. ``stack_on = knowledge.stack_reachable()`` — 栈探活（含 enabled 前置条件）
    2. ``kf = knowledge.client_probe(user.id)`` — 不触发 RAGFlow 开户的轻量客户端
    3. 按 enabled / reachable 组合生成 ``ui_hint``（``KNOWLEDGE_*`` 常量）
    4. 附带 dataset 展示名、KB 标签等前端主题用字段
    """
    settings = get_settings()
    kf = knowledge.client_probe(platform_user_id=user.id)
    stack_on = knowledge.stack_reachable()
    ui_hint = ""
    if settings.knowflow_enabled and not stack_on:
        ui_hint = KNOWLEDGE_SERVICE_UNAVAILABLE
    elif not settings.knowflow_enabled:
        ui_hint = KNOWLEDGE_NOT_ENABLED
    return {
        "knowflow_enabled": stack_on,
        "knowflow_ready": kf.enabled(),
        "health": kf.health(),
        "integration_phase": 4,
        "ui_hint": ui_hint,
        "dataset_name": dataset_display_label_personal(db, user.id),
        "knowflow_kb_labels": knowflow_kb_labels_for_user(db, user),
        "dept_suffix_labels": dept_suffix_labels_for_theme(db, user),
        "features": [
            "knowflow_native_ui",
            "citation_trace",
            "pdf_page_bbox",
            "knowflow_api",
            "per_user_dataset",
            "doc_sync",
        ],
    }
