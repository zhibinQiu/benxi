"""知识图谱（KG）API 路由 — Neo4j 版。

管理实例层（ABox）的实体/关系 CRUD，图谱可视化，LLM 抽取。
所有数据存储在 Neo4j 图数据库中。
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user, require_feature
from app.core.exceptions import bad_request, not_found
from app.core.neo4j import get_neo4j
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.kg import (
    ClearOut,
    EntityIn,
    EntityOut,
    EntityUpdate,
    ExtractBatchIn,
    ExtractBatchOut,
    ExtractFromTextIn,
    ExtractFromTextOut,
    GraphOut,
    GraphReasonIn,
    KgQaContext,
    MetaOut,
    RelationIn,
    RelationOut,
    RelationUpdate,
)
from app.services.kg_extraction_service import extract_kg_from_text_v2
from app.services.kg_reasoning import KGReasoningEngine
from app.services.kg_service import KgService
from app.database import get_db
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/kg",
    tags=["kg"],
    dependencies=[Depends(require_feature("kg"))],
)


async def _get_kg_svc() -> KgService:
    driver = await get_neo4j()
    return KgService(driver)


async def _get_reasoning() -> KGReasoningEngine:
    driver = await get_neo4j()
    return KGReasoningEngine(driver)


# ── 元数据 ────────────────────────────────────────────────────────────────────


@router.get("/meta", response_model=ApiResponse[MetaOut])
async def kg_meta(
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[MetaOut]:
    """获取知识图谱概览。"""
    svc = await _get_kg_svc()
    meta = await svc.get_meta(str(user.id))
    return ApiResponse(data=meta)


# ── 实体 CRUD ────────────────────────────────────────────────────────────────


@router.get("/entities", response_model=ApiResponse[list[EntityOut]])
async def list_entities(
    user: Annotated[User, Depends(get_current_user)],
    type_code: str | None = None,
    q: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[list[EntityOut]]:
    """列出实体，支持按类型和关键词过滤。"""
    svc = await _get_kg_svc()
    items = await svc.list_entities(
        str(user.id), type_code=type_code, q=q, limit=limit, offset=offset
    )
    return ApiResponse(data=items)


@router.get("/entities/{entity_id}", response_model=ApiResponse[EntityOut])
async def get_entity(
    entity_id: str,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[EntityOut]:
    """获取实体详情。"""
    svc = await _get_kg_svc()
    item = await svc.get_entity(entity_id, str(user.id))
    if not item:
        raise not_found("实体不存在")
    return ApiResponse(data=item)


@router.post("/entities", response_model=ApiResponse[EntityOut])
async def create_entity(
    body: EntityIn,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[EntityOut]:
    """创建实体实例。"""
    svc = await _get_kg_svc()
    try:
        item = await svc.create_entity(body, str(user.id))
        return ApiResponse(data=item)
    except ValueError as exc:
        raise bad_request(str(exc))


@router.patch("/entities/{entity_id}", response_model=ApiResponse[EntityOut])
async def update_entity(
    entity_id: str,
    body: EntityUpdate,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[EntityOut]:
    """更新实体。"""
    svc = await _get_kg_svc()
    try:
        item = await svc.update_entity(entity_id, body, str(user.id))
        if not item:
            raise not_found("实体不存在")
        return ApiResponse(data=item)
    except ValueError as exc:
        raise bad_request(str(exc))


@router.delete("/entities/{entity_id}", response_model=ApiResponse[None])
async def delete_entity(
    entity_id: str,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[None]:
    """删除实体及其关联关系。"""
    svc = await _get_kg_svc()
    deleted = await svc.delete_entity(entity_id, str(user.id))
    if not deleted:
        raise not_found("实体不存在")
    return ApiResponse(data=None)


# ── 关系 CRUD ────────────────────────────────────────────────────────────────


@router.get("/relations", response_model=ApiResponse[list[RelationOut]])
async def list_relations(
    user: Annotated[User, Depends(get_current_user)],
    entity_id: str | None = None,
    type_code: str | None = None,
) -> ApiResponse[list[RelationOut]]:
    """列出关系，支持按实体和类型过滤。"""
    svc = await _get_kg_svc()
    items = await svc.list_relations(
        str(user.id), entity_id=entity_id, type_code=type_code
    )
    return ApiResponse(data=items)


@router.post("/relations", response_model=ApiResponse[RelationOut])
async def create_relation(
    body: RelationIn,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[RelationOut]:
    """创建关系实例（自动验证 domain/range 约束）。"""
    svc = await _get_kg_svc()
    try:
        item = await svc.create_relation(body, str(user.id))
        return ApiResponse(data=item)
    except ValueError as exc:
        raise bad_request(str(exc))


@router.delete("/relations/{relation_id}", response_model=ApiResponse[None])
async def delete_relation(
    relation_id: str,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[None]:
    """删除关系。"""
    svc = await _get_kg_svc()
    deleted = await svc.delete_relation(relation_id, str(user.id))
    if not deleted:
        raise not_found("关系不存在")
    return ApiResponse(data=None)


@router.patch("/relations/{relation_id}", response_model=ApiResponse[RelationOut])
async def update_relation(
    relation_id: str,
    body: RelationUpdate,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[RelationOut]:
    """更新关系（类型/描述）。"""
    svc = await _get_kg_svc()
    try:
        item = await svc.update_relation(relation_id, body, str(user.id))
        if not item:
            raise not_found("关系不存在")
        return ApiResponse(data=item)
    except ValueError as exc:
        raise bad_request(str(exc))


# ── 图谱可视化 ────────────────────────────────────────────────────────────────


@router.get("/graph", response_model=ApiResponse[GraphOut])
async def get_graph(
    user: Annotated[User, Depends(get_current_user)],
    focus_entity_id: str | None = None,
    depth: int = Query(default=2, ge=1, le=5),
) -> ApiResponse[GraphOut]:
    """获取子图（按 focus 实体展开）或全图。"""
    svc = await _get_kg_svc()
    if focus_entity_id:
        graph = await svc.get_subgraph(
            focus_entity_id, depth=depth, user_id=str(user.id)
        )
    else:
        graph = await svc.get_full_graph(str(user.id), limit=50)
    return ApiResponse(data=graph)


@router.post("/graph/reason", response_model=ApiResponse[KgQaContext])
async def reason_graph(
    body: GraphReasonIn,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[KgQaContext]:
    """本体感知的多跳推理查询。"""
    engine = await _get_reasoning()
    ctx = await engine.reason(
        question=body.question,
        user_id=str(user.id),
        max_depth=body.depth,
        include_inferred=body.include_inferred,
    )
    return ApiResponse(data=ctx)


# ── 图谱清理 ──────────────────────────────────────────────────────────────────


@router.post("/graph/clear", response_model=ApiResponse[ClearOut])
async def clear_graph(
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[ClearOut]:
    """清除用户所有图谱数据。"""
    svc = await _get_kg_svc()
    result = await svc.clear_user_graph(str(user.id))
    return ApiResponse(data=result)


# ── LLM 抽取 ─────────────────────────────────────────────────────────────────


@router.post("/extract-from-text", response_model=ApiResponse[ExtractFromTextOut])
async def extract_from_text(
    body: ExtractFromTextIn,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[ExtractFromTextOut]:
    """从文本抽取实体/关系（ontology-guided）。"""
    result = await extract_kg_from_text_v2(
        driver=await get_neo4j(),
        title=body.title,
        text=body.text,
        user_id=str(user.id),
        source_type=body.source_type,
        source_id=body.source_id,
    )
    if result.get("skipped"):
        raise bad_request(str(result.get("reason", "抽取失败")))
    return ApiResponse(data=ExtractFromTextOut(**result))


@router.post("/extract/documents", response_model=ApiResponse[dict[str, Any]])
async def extract_documents(
    body: ExtractBatchIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict[str, Any]]:
    """批量读取文档正文并通过 LLM 抽取实体/关系到知识图谱。"""
    svc = await _get_kg_svc()
    stats = await svc.batch_extract_documents_from_content(
        db, str(user.id), max_docs=body.max_docs
    )
    return ApiResponse(data=stats)


@router.post("/extract/batch", response_model=ApiResponse[ExtractBatchOut])
async def extract_batch(
    body: ExtractBatchIn,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[ExtractBatchOut]:
    """批量抽取文档（旧版兼容）。"""
    return ApiResponse(
        data=ExtractBatchOut(
            queued=False,
            reason="请使用 /extract/documents",
            document_count=0,
            total_candidates=0,
        )
    )


# ── 平台数据同步 ──────────────────────────────────────────────────────────


@router.post("/sync/org", response_model=ApiResponse[dict[str, Any]])
async def sync_platform_org(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict[str, Any]]:
    """同步平台用户/部门到知识图谱（person/org 实体 + employs/contains 关系）。"""
    svc = await _get_kg_svc()
    stats = await svc.sync_platform_org(db, str(user.id))
    return ApiResponse(data=stats)


@router.post("/sync/agents", response_model=ApiResponse[dict[str, Any]])
async def sync_platform_agents(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict[str, Any]]:
    """同步平台智能体/工具/Skill 到知识图谱。"""
    svc = await _get_kg_svc()
    stats = await svc.sync_platform_agents(db, str(user.id))
    return ApiResponse(data=stats)


@router.post("/sync/memory", response_model=ApiResponse[dict[str, Any]])
async def sync_agent_memory(
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[dict[str, Any]]:
    """同步智能体记忆到知识图谱。"""
    svc = await _get_kg_svc()
    stats = await svc.sync_agent_memory_to_kg(str(user.id))
    return ApiResponse(data=stats)


@router.post("/sync/all", response_model=ApiResponse[dict[str, Any]])
async def sync_all_platform(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict[str, Any]]:
    """一键同步所有平台数据到知识图谱（组织 + 智能体 + 记忆）。"""
    svc = await _get_kg_svc()
    stats: dict[str, Any] = {}
    try:
        org_stats = await svc.sync_platform_org(db, str(user.id))
        stats.update({f"org_{k}": v for k, v in org_stats.items()})
    except Exception as exc:
        logger.warning("组织同步失败: %s", exc)
        stats["org_error"] = str(exc)[:200]
    try:
        agent_stats = await svc.sync_platform_agents(db, str(user.id))
        stats.update({f"agent_{k}": v for k, v in agent_stats.items()})
    except Exception as exc:
        logger.warning("智能体同步失败: %s", exc)
        stats["agent_error"] = str(exc)[:200]
    try:
        memory_stats = await svc.sync_agent_memory_to_kg(str(user.id))
        stats.update({f"memory_{k}": v for k, v in memory_stats.items()})
    except Exception as exc:
        logger.warning("记忆同步失败: %s", exc)
        stats["memory_error"] = str(exc)[:200]
    return ApiResponse(data=stats)
