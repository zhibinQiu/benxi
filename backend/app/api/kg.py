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
    EntityMergeIn,
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


@router.post("/entities/merge", response_model=ApiResponse[dict])
async def merge_entities(
    body: EntityMergeIn,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[dict]:
    """合并两个实体实例（source → target）。"""
    svc = await _get_kg_svc()
    try:
        result = await svc.merge_entities(body.source_id, body.target_id, str(user.id))
        return ApiResponse(data=result)
    except ValueError as exc:
        raise bad_request(str(exc))


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
    limit: int = Query(default=300, ge=1, le=1000),
) -> ApiResponse[GraphOut]:
    """获取子图（按 focus 实体展开）或全图。全图默认不自动调用，由前端显式刷新触发。"""
    svc = await _get_kg_svc()
    if focus_entity_id:
        graph = await svc.get_subgraph(
            focus_entity_id, depth=depth, user_id=str(user.id)
        )
    else:
        graph = await svc.get_full_graph(str(user.id), limit=limit)
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
        discover_ontology=body.discover_ontology,
    )
    if result.get("skipped"):
        detail = result.get("error") or result.get("reason") or "抽取失败"
        raise bad_request(str(detail))
    return ApiResponse(data=ExtractFromTextOut(**result))


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


# ── 平台数据同步（后台任务）──────────────────────────────────────────────


def _enqueue_sync(
    db: Session,
    user: User,
    *,
    scope: str,
    max_docs: int = 20,
    force: bool = False,
    discover_ontology: bool = True,
) -> dict[str, Any]:
    from app.services.kg_sync_job_service import enqueue_kg_sync_job, scope_label

    try:
        job = enqueue_kg_sync_job(
            db,
            user,
            scope=scope,
            max_docs=max_docs,
            force=force,
            discover_ontology=discover_ontology,
        )
    except ValueError as exc:
        raise bad_request(str(exc)) from exc
    return {
        "queued": True,
        "job_id": str(job.id),
        "scope": scope,
        "scope_label": scope_label(scope),
        "message": f"已加入后台任务：知识图谱同步 · {scope_label(scope)}",
    }


@router.post("/sync/org", response_model=ApiResponse[dict[str, Any]])
def sync_platform_org(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict[str, Any]]:
    """将平台用户/部门同步到知识图谱（后台任务）。"""
    return ApiResponse(data=_enqueue_sync(db, user, scope="org"))


@router.post("/sync/agents", response_model=ApiResponse[dict[str, Any]])
def sync_platform_agents(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict[str, Any]]:
    """将平台智能体/工具/Skill 同步到知识图谱（后台任务）。"""
    return ApiResponse(data=_enqueue_sync(db, user, scope="agents"))


@router.post("/sync/memory", response_model=ApiResponse[dict[str, Any]])
def sync_agent_memory(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict[str, Any]]:
    """将智能体记忆同步到知识图谱（后台任务）。"""
    return ApiResponse(data=_enqueue_sync(db, user, scope="memory"))


@router.post("/sync/all", response_model=ApiResponse[dict[str, Any]])
def sync_all_platform(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict[str, Any]]:
    """一键全量同步（组织+智能体+记忆+文档抽取）到知识图谱（后台任务）。"""
    return ApiResponse(data=_enqueue_sync(db, user, scope="all"))


@router.post("/extract/documents", response_model=ApiResponse[dict[str, Any]])
def extract_documents(
    body: ExtractBatchIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict[str, Any]]:
    """批量文档 LLM 抽取（后台任务）：本体发现 + 约束实例抽取。"""
    return ApiResponse(
        data=_enqueue_sync(
            db,
            user,
            scope="extract",
            max_docs=body.max_docs,
            force=body.force,
            discover_ontology=body.discover_ontology,
        )
    )
