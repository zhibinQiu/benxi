"""知识图谱 API — 本体图谱查询与编辑。"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_feature
from app.core.exceptions import bad_request
from app.database import get_db
from app.models.org import User
from app.schemas.common import ApiResponse
from app.schemas.kg import (
    KgEntityIn,
    KgEntityOut,
    KgEntityTypeIn,
    KgEntityTypeOut,
    KgEntityTypeUpdate,
    KgEntityUpdate,
    KgExtractFromTextIn,
    KgExtractFromTextOut,
    KgGraphOut,
    KgMetaOut,
    KgRelationIn,
    KgRelationOut,
    KgRelationTypeIn,
    KgRelationTypeOut,
    KgRelationTypeUpdate,
)
from app.services import kg_service
from app.services.kg_extraction_service import extract_kg_from_text

router = APIRouter(
    prefix="/kg",
    tags=["kg"],
    dependencies=[Depends(require_feature("kg_palantir"))],
)


@router.get("/meta", response_model=ApiResponse[KgMetaOut])
def kg_meta(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    sync_system: bool = Query(True, description="是否同步平台用户与部门到图谱"),
) -> ApiResponse[KgMetaOut]:
    return ApiResponse(data=kg_service.get_meta(db, user, sync_system=sync_system))


@router.post("/extract-from-text", response_model=ApiResponse[KgExtractFromTextOut])
def kg_extract_from_text(
    body: KgExtractFromTextIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[KgExtractFromTextOut]:
    result = extract_kg_from_text(
        db,
        user,
        title=body.title,
        text=body.text,
        source_type=body.source_type,
        source_id=body.source_id,
    )
    if result.get("skipped"):
        reason = str(result.get("reason") or "unknown")
        messages = {
            "kg_extraction_disabled": "本体图谱抽取未启用，请联系管理员配置语言模型",
            "no_kg_permission": "无本体图谱权限",
            "text_too_short": "总结内容过短，无法抽取实体关系",
            "llm_failed": f"抽取失败：{result.get('error', '')}",
        }
        raise bad_request(messages.get(reason, reason))
    return ApiResponse(data=KgExtractFromTextOut(**result))


@router.get("/entities", response_model=ApiResponse[list[KgEntityOut]])
def kg_list_entities(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    type_id: UUID | None = None,
    q: str | None = None,
) -> ApiResponse[list[KgEntityOut]]:
    return ApiResponse(
        data=kg_service.list_entities(db, user, type_id=type_id, q=q)
    )


@router.get("/entities/{entity_id}", response_model=ApiResponse[KgEntityOut])
def kg_get_entity(
    entity_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[KgEntityOut]:
    return ApiResponse(data=kg_service.get_entity(db, user, entity_id))


@router.post(
    "/entities/from-document/{document_id}",
    response_model=ApiResponse[KgEntityOut],
)
def kg_create_entity_from_document(
    document_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[KgEntityOut]:
    return ApiResponse(
        data=kg_service.ensure_doc_entity_for_document(db, user, document_id)
    )


@router.post("/entities", response_model=ApiResponse[KgEntityOut])
def kg_create_entity(
    body: KgEntityIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[KgEntityOut]:
    return ApiResponse(data=kg_service.create_entity(db, user, body))


@router.patch("/entities/{entity_id}", response_model=ApiResponse[KgEntityOut])
def kg_update_entity(
    entity_id: UUID,
    body: KgEntityUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[KgEntityOut]:
    return ApiResponse(data=kg_service.update_entity(db, user, entity_id, body))


@router.delete("/entities/{entity_id}", response_model=ApiResponse[None])
def kg_delete_entity(
    entity_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[None]:
    kg_service.delete_entity(db, user, entity_id)
    return ApiResponse(data=None)


@router.get("/relations", response_model=ApiResponse[list[KgRelationOut]])
def kg_list_relations(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    entity_id: UUID | None = None,
) -> ApiResponse[list[KgRelationOut]]:
    return ApiResponse(
        data=kg_service.list_relations(db, user, entity_id=entity_id)
    )


@router.post("/relations", response_model=ApiResponse[KgRelationOut])
def kg_create_relation(
    body: KgRelationIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[KgRelationOut]:
    return ApiResponse(data=kg_service.create_relation(db, user, body))


@router.delete("/relations/{relation_id}", response_model=ApiResponse[None])
def kg_delete_relation(
    relation_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[None]:
    kg_service.delete_relation(db, user, relation_id)
    return ApiResponse(data=None)


@router.get("/graph", response_model=ApiResponse[KgGraphOut])
def kg_graph(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    focus_entity_id: UUID | None = None,
    depth: Annotated[int, Query(ge=1, le=3)] = 1,
) -> ApiResponse[KgGraphOut]:
    return ApiResponse(
        data=kg_service.get_graph(
            db,
            user,
            focus_entity_id=focus_entity_id,
            depth=depth,
        )
    )


@router.post("/entity-types", response_model=ApiResponse[KgEntityTypeOut])
def kg_create_entity_type(
    body: KgEntityTypeIn,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[KgEntityTypeOut]:
    return ApiResponse(data=kg_service.create_entity_type(db, body))


@router.patch("/entity-types/{type_id}", response_model=ApiResponse[KgEntityTypeOut])
def kg_update_entity_type(
    type_id: UUID,
    body: KgEntityTypeUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[KgEntityTypeOut]:
    return ApiResponse(data=kg_service.update_entity_type(db, type_id, body))


@router.delete("/entity-types/{type_id}", response_model=ApiResponse[None])
def kg_delete_entity_type(
    type_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[None]:
    kg_service.delete_entity_type(db, type_id)
    return ApiResponse(data=None)


@router.post("/relation-types", response_model=ApiResponse[KgRelationTypeOut])
def kg_create_relation_type(
    body: KgRelationTypeIn,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[KgRelationTypeOut]:
    return ApiResponse(data=kg_service.create_relation_type(db, body))


@router.patch("/relation-types/{type_id}", response_model=ApiResponse[KgRelationTypeOut])
def kg_update_relation_type(
    type_id: UUID,
    body: KgRelationTypeUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[KgRelationTypeOut]:
    return ApiResponse(data=kg_service.update_relation_type(db, type_id, body))


@router.delete("/relation-types/{type_id}", response_model=ApiResponse[None])
def kg_delete_relation_type(
    type_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[None]:
    kg_service.delete_relation_type(db, type_id)
    return ApiResponse(data=None)
