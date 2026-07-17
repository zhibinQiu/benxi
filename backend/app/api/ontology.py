"""本体定义（Ontology）API 路由。

管理本体层（TBox）的实体类型、关系类型和公理规则。
所有数据通过 Neo4j 图数据库存储。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_feature
from app.core.exceptions import bad_request, not_found
from app.core.neo4j import get_neo4j
from app.database import get_db
from app.models.document import Document
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.ontology import (
    AxiomIn,
    AxiomOut,
    AxiomRunResult,
    AxiomUpdate,
    DefaultSeedIn,
    EntityTypeIn,
    EntityTypeOut,
    EntityTypeUpdate,
    MetaOut,
    RelationTypeIn,
    RelationTypeOut,
    RelationTypeUpdate,
    ValidateInput,
    ValidateOutput,
)
from app.services.ontology_service import OntologyService
from app.services.kg_service import KgService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/ontology",
    tags=["ontology"],
    dependencies=[Depends(require_feature("ontology"))],
)


async def _get_ontology_svc() -> OntologyService:
    """创建 OntologyService 实例（使用全局 Neo4j driver）。"""
    driver = await get_neo4j()
    return OntologyService(driver)


async def _get_kg_svc() -> KgService:
    """创建 KgService 实例（使用全局 Neo4j driver）。"""
    driver = await get_neo4j()
    return KgService(driver)


# ── 元数据 ────────────────────────────────────────────────────────────────────


@router.get("/meta", response_model=ApiResponse[MetaOut])
async def ontology_meta(
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[MetaOut]:
    """获取本体概览信息。"""
    svc = await _get_ontology_svc()
    meta = await svc.get_meta()
    return ApiResponse(data=meta)


# ── 实体类型 ──────────────────────────────────────────────────────────────────


@router.get("/entity-types", response_model=ApiResponse[list[EntityTypeOut]])
async def list_entity_types(
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[list[EntityTypeOut]]:
    """列出所有实体类型定义。"""
    svc = await _get_ontology_svc()
    items = await svc.list_entity_types()
    return ApiResponse(data=items)


@router.post("/entity-types", response_model=ApiResponse[EntityTypeOut])
async def create_entity_type(
    body: EntityTypeIn,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[EntityTypeOut]:
    """创建实体类型定义。"""
    svc = await _get_ontology_svc()
    try:
        item = await svc.create_entity_type(body)
        return ApiResponse(data=item)
    except ValueError as exc:
        raise bad_request(str(exc))


@router.get("/entity-types/{code}", response_model=ApiResponse[EntityTypeOut])
async def get_entity_type(
    code: Annotated[str, Path(pattern="^[a-z][a-z0-9_]*$")],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[EntityTypeOut]:
    """获取单个实体类型定义。"""
    svc = await _get_ontology_svc()
    item = await svc.get_entity_type(code)
    if not item:
        raise not_found(f"实体类型 '{code}' 不存在")
    return ApiResponse(data=item)


@router.patch("/entity-types/{code}", response_model=ApiResponse[EntityTypeOut])
async def update_entity_type(
    code: Annotated[str, Path(pattern="^[a-z][a-z0-9_]*$")],
    body: EntityTypeUpdate,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[EntityTypeOut]:
    """更新实体类型定义。"""
    svc = await _get_ontology_svc()
    item = await svc.update_entity_type(code, body)
    if not item:
        raise not_found(f"实体类型 '{code}' 不存在")
    return ApiResponse(data=item)


@router.delete("/entity-types/{code}", response_model=ApiResponse[None])
async def delete_entity_type(
    code: Annotated[str, Path(pattern="^[a-z][a-z0-9_]*$")],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[None]:
    """删除实体类型定义。"""
    svc = await _get_ontology_svc()
    try:
        deleted = await svc.delete_entity_type(code)
        if not deleted:
            raise not_found(f"实体类型 '{code}' 不存在")
        return ApiResponse(data=None)
    except ValueError as exc:
        raise bad_request(str(exc))


@router.post(
    "/entity-types/{code}/validate",
    response_model=ApiResponse[ValidateOutput],
)
async def validate_entity_properties(
    code: Annotated[str, Path(pattern="^[a-z][a-z0-9_]*$")],
    body: ValidateInput,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[ValidateOutput]:
    """验证实体属性是否符合本体的 property_schema。"""
    svc = await _get_ontology_svc()
    errors = await svc.validate_entity_properties(code, body.properties or {})
    return ApiResponse(
        data=ValidateOutput(
            valid=len(errors) == 0,
            errors=errors,
        )
    )


# ── 关系类型 ──────────────────────────────────────────────────────────────────


@router.get("/relation-types", response_model=ApiResponse[list[RelationTypeOut]])
async def list_relation_types(
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[list[RelationTypeOut]]:
    """列出所有关系类型定义。"""
    svc = await _get_ontology_svc()
    items = await svc.list_relation_types()
    return ApiResponse(data=items)


@router.post("/relation-types", response_model=ApiResponse[RelationTypeOut])
async def create_relation_type(
    body: RelationTypeIn,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[RelationTypeOut]:
    """创建关系类型定义。"""
    svc = await _get_ontology_svc()
    try:
        item = await svc.create_relation_type(body)
        return ApiResponse(data=item)
    except ValueError as exc:
        raise bad_request(str(exc))


@router.get("/relation-types/{code}", response_model=ApiResponse[RelationTypeOut])
async def get_relation_type(
    code: Annotated[str, Path(pattern="^[a-z][a-z0-9_]*$")],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[RelationTypeOut]:
    """获取单个关系类型定义。"""
    svc = await _get_ontology_svc()
    item = await svc.get_relation_type(code)
    if not item:
        raise not_found(f"关系类型 '{code}' 不存在")
    return ApiResponse(data=item)


@router.patch("/relation-types/{code}", response_model=ApiResponse[RelationTypeOut])
async def update_relation_type(
    code: Annotated[str, Path(pattern="^[a-z][a-z0-9_]*$")],
    body: RelationTypeUpdate,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[RelationTypeOut]:
    """更新关系类型定义。"""
    svc = await _get_ontology_svc()
    item = await svc.update_relation_type(code, body)
    if not item:
        raise not_found(f"关系类型 '{code}' 不存在")
    return ApiResponse(data=item)


@router.delete("/relation-types/{code}", response_model=ApiResponse[None])
async def delete_relation_type(
    code: Annotated[str, Path(pattern="^[a-z][a-z0-9_]*$")],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[None]:
    """删除关系类型定义。"""
    svc = await _get_ontology_svc()
    try:
        deleted = await svc.delete_relation_type(code)
        if not deleted:
            raise not_found(f"关系类型 '{code}' 不存在")
        return ApiResponse(data=None)
    except ValueError as exc:
        raise bad_request(str(exc))


# ── 公理管理 ──────────────────────────────────────────────────────────────────


@router.get("/axioms", response_model=ApiResponse[list[AxiomOut]])
async def list_axioms(
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[list[AxiomOut]]:
    """列出所有公理规则。"""
    svc = await _get_ontology_svc()
    items = await svc.list_axioms()
    return ApiResponse(data=items)


@router.post("/axioms", response_model=ApiResponse[AxiomOut])
async def create_axiom(
    body: AxiomIn,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[AxiomOut]:
    """创建公理规则。"""
    svc = await _get_ontology_svc()
    try:
        item = await svc.create_axiom(body)
        return ApiResponse(data=item)
    except ValueError as exc:
        raise bad_request(str(exc))


@router.get("/axioms/{name}", response_model=ApiResponse[AxiomOut])
async def get_axiom(
    name: str,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[AxiomOut]:
    """获取单个公理规则。"""
    svc = await _get_ontology_svc()
    item = await svc.get_axiom(name)
    if not item:
        raise not_found(f"公理 '{name}' 不存在")
    return ApiResponse(data=item)


@router.patch("/axioms/{name}", response_model=ApiResponse[AxiomOut])
async def update_axiom(
    name: str,
    body: AxiomUpdate,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[AxiomOut]:
    """更新公理规则。"""
    svc = await _get_ontology_svc()
    item = await svc.update_axiom(name, body)
    if not item:
        raise not_found(f"公理 '{name}' 不存在")
    return ApiResponse(data=item)


@router.delete("/axioms/{name}", response_model=ApiResponse[None])
async def delete_axiom(
    name: str,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[None]:
    """删除公理规则。"""
    svc = await _get_ontology_svc()
    deleted = await svc.delete_axiom(name)
    if not deleted:
        raise not_found(f"公理 '{name}' 不存在")
    return ApiResponse(data=None)


@router.post("/axioms/{name}/run", response_model=ApiResponse[AxiomRunResult])
async def run_axiom(
    name: str,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[AxiomRunResult]:
    """执行指定公理规则。"""
    svc = await _get_ontology_svc()
    result = await svc.run_axiom(name)
    return ApiResponse(data=result)


@router.post("/axioms/run-all", response_model=ApiResponse[list[AxiomRunResult]])
async def run_all_axioms(
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[list[AxiomRunResult]]:
    """执行所有活跃公理规则。"""
    svc = await _get_ontology_svc()
    results = await svc.run_all_active_axioms()
    return ApiResponse(data=results)


# ── 默认种子 ──────────────────────────────────────────────────────────────────


@router.post("/seed-defaults", response_model=ApiResponse[dict[str, int]])
async def seed_defaults(
    body: DefaultSeedIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[dict[str, int]]:
    """初始化默认本体，并从知识库和平台库同步文档到图谱。"""
    if not body.confirm:
        raise bad_request("请确认初始化操作")
    svc = await _get_ontology_svc()
    stats = await svc.seed_defaults(overwrite=False)

    # 从知识库同步文档到图谱
    try:
        kg_svc = await _get_kg_svc()
        rows = db.execute(
            select(Document).where(Document.deleted_at.is_(None))
        ).scalars().all()
        doc_tuples: list[tuple[str, str, str, str]] = [
            (str(doc.id), doc.title, doc.description, str(doc.owner_id))
            for doc in rows
        ]
        import_stats = await kg_svc.batch_import_documents(doc_tuples)
        stats["documents_imported"] = import_stats["imported"]
        stats["documents_skipped"] = import_stats["skipped"]
    except Exception as exc:
        logger.warning("同步文档到图谱失败: %s", exc)
        stats["documents_imported"] = 0
        stats["documents_skipped"] = 0
        stats["sync_error"] = str(exc)[:200]

    # 同步平台组织数据（用户/部门）
    try:
        kg_svc = await _get_kg_svc()
        org_stats = await kg_svc.sync_platform_org(db, str(user.id))
        stats.update({f"org_{k}": v for k, v in org_stats.items()})
    except Exception as exc:
        logger.warning("同步组织数据到图谱失败: %s", exc)
        stats["org_error"] = str(exc)[:200]

    # 同步智能体/工具/Skill
    try:
        kg_svc = await _get_kg_svc()
        agent_stats = await kg_svc.sync_platform_agents(db, str(user.id))
        stats.update({f"agent_{k}": v for k, v in agent_stats.items()})
    except Exception as exc:
        logger.warning("同步智能体数据到图谱失败: %s", exc)
        stats["agent_error"] = str(exc)[:200]

    # 同步智能体记忆
    try:
        kg_svc = await _get_kg_svc()
        memory_stats = await kg_svc.sync_agent_memory_to_kg(str(user.id))
        stats.update({f"memory_{k}": v for k, v in memory_stats.items()})
    except Exception as exc:
        logger.warning("同步记忆到图谱失败: %s", exc)
        stats["memory_error"] = str(exc)[:200]

    return ApiResponse(data=stats)
