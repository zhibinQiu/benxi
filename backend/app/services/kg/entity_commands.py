"""图谱实体写操作：按筛选条件批量删除、清空用户图谱。"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import bad_request
from app.core.platform_cache import invalidate_kg_cache
from app.models.kg import KgEntity, KgRelation
from app.models.org import User


def _invalidate_kg_cache(user_id: uuid.UUID) -> None:
    invalidate_kg_cache(user_id)


def _matching_entity_ids(
    db: Session,
    user: User,
    *,
    entity_ids: list[uuid.UUID] | None = None,
    type_id: uuid.UUID | None = None,
    q: str | None = None,
) -> list[uuid.UUID]:
    if entity_ids:
        rows = db.scalars(
            select(KgEntity.id).where(
                KgEntity.owner_id == user.id,
                KgEntity.id.in_(entity_ids),
            )
        ).all()
        return list(rows)

    stmt = select(KgEntity.id).where(KgEntity.owner_id == user.id)
    if type_id:
        stmt = stmt.where(KgEntity.type_id == type_id)
    if q and q.strip():
        kw = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(KgEntity.name.ilike(kw), KgEntity.description.ilike(kw))
        )
    return list(db.scalars(stmt).all())


def batch_delete_entities(
    db: Session,
    user: User,
    *,
    entity_ids: list[uuid.UUID] | None = None,
    type_id: uuid.UUID | None = None,
    q: str | None = None,
) -> int:
    """按 id 列表或当前筛选条件（type_id + q）批量删除实体；关联关系随实体级联删除。"""
    if not entity_ids and not type_id and not (q and q.strip()):
        raise bad_request("请指定要删除的实体，或提供类型/搜索筛选条件")

    ids = _matching_entity_ids(
        db, user, entity_ids=entity_ids, type_id=type_id, q=q
    )
    if not ids:
        return 0

    db.execute(delete(KgEntity).where(KgEntity.id.in_(ids)))
    db.commit()
    _invalidate_kg_cache(user.id)
    return len(ids)


def clear_user_graph(db: Session, user: User) -> dict[str, int]:
    """删除当前用户拥有的全部实体与关系。"""
    entity_count = int(
        db.scalar(
            select(func.count()).select_from(KgEntity).where(KgEntity.owner_id == user.id)
        )
        or 0
    )
    relation_count = int(
        db.scalar(
            select(func.count()).select_from(KgRelation).where(KgRelation.owner_id == user.id)
        )
        or 0
    )
    if entity_count == 0 and relation_count == 0:
        return {"deleted_entities": 0, "deleted_relations": 0}

    db.execute(delete(KgRelation).where(KgRelation.owner_id == user.id))
    db.execute(delete(KgEntity).where(KgEntity.owner_id == user.id))
    db.commit()
    _invalidate_kg_cache(user.id)
    return {
        "deleted_entities": entity_count,
        "deleted_relations": relation_count,
    }
