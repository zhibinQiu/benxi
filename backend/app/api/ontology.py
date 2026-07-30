"""本体定义（Ontology）API 路由。

管理全局本体层（TBox）：实体类型、关系类型、公理规则存 GraphDB；
实例计数与公理 Cypher 执行仍使用 Neo4j。
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response
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
    FieldBindingDiscoverOut,
    FieldBindingOut,
    FieldBindingSchemaOut,
    FieldBindingUpdate,
    FieldBindingUpsert,
    MergeTypesIn,
    MetaOut,
    OntologyDiscoverApplyIn,
    OntologyDiscoverFromDocumentsIn,
    OntologyDiscoverFromTextIn,
    OntologyDiscoverResultOut,
    RelationTypeIn,
    RelationTypeOut,
    RelationTypeUpdate,
    SchemaGraphOut,
    ValidateInput,
    ValidateOutput,
)
from app.services.kg_service import KgService
from app.services.ontology_extraction_service import (
    apply_ontology_candidates,
    discover_ontology_candidates,
    discover_ontology_from_documents,
)
from app.services.ontology_factory import get_ontology_service
from app.services.ontology_service import OntologyService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/ontology",
    tags=["ontology"],
    dependencies=[Depends(require_feature("ontology"))],
)


async def _get_ontology_svc() -> OntologyService:
    return await get_ontology_service()


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


@router.get("/schema-graph", response_model=ApiResponse[SchemaGraphOut])
async def ontology_schema_graph(
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[SchemaGraphOut]:
    """本体 TBox 可视化图（Class / Property / subClassOf）。"""
    svc = await _get_ontology_svc()
    graph = await svc.get_schema_graph()
    return ApiResponse(data=graph)


# ── 实体类型 ──────────────────────────────────────────────────────────────────


@router.get("/entity-types", response_model=ApiResponse[list[EntityTypeOut]])
async def list_entity_types(
    user: Annotated[User, Depends(get_current_user)],
    include_counts: bool = Query(default=False),
) -> ApiResponse[list[EntityTypeOut]]:
    """列出所有实体类型定义。默认不查 Neo4j 实例数，加快 TBox 加载。"""
    svc = await _get_ontology_svc()
    items = await svc.list_entity_types(include_counts=include_counts)
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
    include_counts: bool = Query(default=False),
) -> ApiResponse[list[RelationTypeOut]]:
    """列出所有关系类型定义。默认不查 Neo4j 实例数。"""
    svc = await _get_ontology_svc()
    items = await svc.list_relation_types(include_counts=include_counts)
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


@router.post("/rebuild-shapes", response_model=ApiResponse[dict[str, Any]])
async def rebuild_shapes(
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[dict[str, Any]]:
    """为全部概念重建 OWL DatatypeProperty + SHACL NodeShape。"""
    svc = await _get_ontology_svc()
    stats = await svc.rebuild_shapes_for_all()
    return ApiResponse(data=stats)


@router.get("/export")
async def export_ontology(
    user: Annotated[User, Depends(get_current_user)],
    format: str = Query(default="ttl"),
) -> Response:
    """导出本体 Turtle（OWL + SHACL）。"""
    if format not in ("ttl", "turtle"):
        raise bad_request("仅支持 format=ttl")
    svc = await _get_ontology_svc()
    ttl = await svc.export_ttl()
    return Response(
        content=ttl,
        media_type="text/turtle; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="ontology.ttl"'},
    )


@router.post("/merge-types", response_model=ApiResponse[dict[str, Any]])
async def merge_types(
    body: MergeTypesIn,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[dict[str, Any]]:
    """合并两个实体类型（source → target），迁移同义词与关系引用。"""
    svc = await _get_ontology_svc()
    try:
        result = await svc.merge_entity_types(body.source_code, body.target_code)
        return ApiResponse(data=result)
    except ValueError as exc:
        raise bad_request(str(exc))


@router.post("/seed-defaults", response_model=ApiResponse[dict[str, Any]])
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


# ── LLM TBox 发现 ───────────────────────────────────────────────────────────


@router.post(
    "/discover-from-text",
    response_model=ApiResponse[OntologyDiscoverResultOut],
)
async def ontology_discover_from_text(
    body: OntologyDiscoverFromTextIn,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[OntologyDiscoverResultOut]:
    """从正文 LLM 发现概念/关系候选（不写库）。"""
    _ = user
    svc = await _get_ontology_svc()
    data = await discover_ontology_candidates(
        svc,
        title=body.title,
        text=body.text,
        max_chars=body.max_chars,
    )
    return ApiResponse(data=OntologyDiscoverResultOut.model_validate(data))


@router.post(
    "/discover-from-documents",
    response_model=ApiResponse[OntologyDiscoverResultOut],
)
async def ontology_discover_from_documents(
    body: OntologyDiscoverFromDocumentsIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[OntologyDiscoverResultOut]:
    """从平台文档拼正文后发现本体候选（不写库）。"""
    svc = await _get_ontology_svc()
    data = await discover_ontology_from_documents(
        svc,
        db,
        user,
        document_ids=list(body.document_ids),
        max_chars=body.max_chars,
    )
    return ApiResponse(data=OntologyDiscoverResultOut.model_validate(data))


@router.post("/discover-from-text/apply", response_model=ApiResponse[dict[str, Any]])
async def ontology_discover_apply(
    body: OntologyDiscoverApplyIn,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[dict[str, Any]]:
    """将勾选的 TBox 候选写入 GraphDB。"""
    _ = user
    svc = await _get_ontology_svc()
    selected_et = [
        e.model_dump()
        for e in body.entity_types
        if e.selected and e.action in ("create", "merge")
    ]
    selected_rt = [
        r.model_dump()
        for r in body.relation_types
        if r.selected and r.action == "create"
    ]
    if not selected_et and not selected_rt:
        raise bad_request("请至少勾选一项候选")
    stats = await apply_ontology_candidates(
        svc,
        entity_types=selected_et,
        relation_types=selected_rt,
    )
    return ApiResponse(data=stats)


# ── 问数映射（自动发现，非 TBox）────────────────────────────────


@router.get("/field-bindings/schema", response_model=ApiResponse[FieldBindingSchemaOut])
async def field_bindings_schema(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    _feat: Annotated[None, Depends(require_feature("ontology"))],
):
    """受控 SQL 表白名单（可选）；文档抽取类本体可无映射。"""
    _ = user
    from app.services.semantic_field_binding_service import sql_schema_for_editor

    try:
        data = sql_schema_for_editor(db)
    except Exception:
        logger.exception("field-bindings schema unavailable")
        data = {"tables": {}, "join_templates": []}
    return ApiResponse(data=FieldBindingSchemaOut(**data))


@router.get("/field-bindings", response_model=ApiResponse[list[FieldBindingOut]])
async def list_field_bindings(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    _feat: Annotated[None, Depends(require_feature("ontology"))],
    enabled_only: bool = Query(default=False),
):
    """问数 SQL 映射列表；无表/无数据时返回空列表（非必需）。"""
    _ = user
    from app.services.semantic_field_binding_service import (
        bindings_as_dicts,
        ensure_bindings_populated,
        list_bindings,
    )

    try:
        ensure_bindings_populated(db)
        rows = list_bindings(db, enabled_only=enabled_only)
        return ApiResponse(data=[FieldBindingOut(**x) for x in bindings_as_dicts(rows)])
    except Exception:
        logger.exception("field-bindings list unavailable")
        return ApiResponse(data=[])


@router.post(
    "/field-bindings/discover",
    response_model=ApiResponse[FieldBindingDiscoverOut],
)
async def discover_field_bindings(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    _feat: Annotated[None, Depends(require_feature("ontology"))],
):
    _ = user
    from app.services.semantic_field_binding_service import (
        bindings_as_dicts,
        list_bindings,
        upsert_discovered,
    )

    stats = upsert_discovered(db)
    rows = list_bindings(db)
    return ApiResponse(
        data=FieldBindingDiscoverOut(
            **stats,
            items=[FieldBindingOut(**x) for x in bindings_as_dicts(rows)],
        )
    )


@router.put("/field-bindings", response_model=ApiResponse[FieldBindingOut])
async def put_field_binding(
    body: FieldBindingUpsert,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    _feat: Annotated[None, Depends(require_feature("ontology"))],
):
    _ = user
    from app.services.semantic_field_binding_service import (
        bindings_as_dicts,
        upsert_binding_manual,
    )

    row = upsert_binding_manual(
        db,
        concept=body.concept,
        property_key=body.property_key,
        source=body.source,
        table_name=body.table_name,
        column_name=body.column_name,
        join_template=body.join_template,
        notes=body.notes,
        enabled=body.enabled,
        status=body.status,
    )
    return ApiResponse(data=FieldBindingOut(**bindings_as_dicts([row])[0]))


@router.patch(
    "/field-bindings/{binding_id}",
    response_model=ApiResponse[FieldBindingOut],
)
async def patch_field_binding(
    binding_id: Annotated[str, Path(min_length=1)],
    body: FieldBindingUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    _feat: Annotated[None, Depends(require_feature("ontology"))],
):
    _ = user
    from app.services.semantic_field_binding_service import (
        bindings_as_dicts,
        update_binding,
    )

    row = update_binding(
        db,
        binding_id,
        table_name=body.table_name,
        column_name=body.column_name,
        join_template=body.join_template,
        enabled=body.enabled,
        status=body.status,
        notes=body.notes,
    )
    if not row:
        raise not_found("映射不存在")
    return ApiResponse(data=FieldBindingOut(**bindings_as_dicts([row])[0]))
