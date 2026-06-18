"""将平台用户、部门组织树同步到当前用户的知识图谱实体。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.kg import KgEntity, KgRelation, KgRelationType
from app.models.org import Department, User, UserDepartment, UserStatus
from app.services.kg_service import ensure_ontology_defaults

USER_ID_PROP = "platform_user_id"
DEPT_ID_PROP = "platform_department_id"


def _type_by_code(db: Session) -> dict[str, uuid.UUID]:
    from app.models.kg import KgEntityType

    rows = db.scalars(select(KgEntityType)).all()
    return {t.code: t.id for t in rows}


def _rel_type_id(db: Session, code: str) -> uuid.UUID | None:
    row = db.scalar(select(KgRelationType.id).where(KgRelationType.code == code))
    return row


def _find_entity_by_prop(
    db: Session,
    user: User,
    *,
    prop_key: str,
    prop_value: str,
) -> KgEntity | None:
    rows = db.scalars(
        select(KgEntity).where(KgEntity.owner_id == user.id)
    ).all()
    for row in rows:
        props = row.properties or {}
        if str(props.get(prop_key) or "") == prop_value:
            return row
    return None


def _upsert_entity(
    db: Session,
    user: User,
    *,
    type_id: uuid.UUID,
    name: str,
    description: str,
    prop_key: str,
    prop_value: str,
    extra_props: dict | None = None,
) -> KgEntity:
    row = _find_entity_by_prop(db, user, prop_key=prop_key, prop_value=prop_value)
    props = {prop_key: prop_value, **(extra_props or {})}
    if row:
        row.name = name.strip()[:256]
        row.description = description or ""
        merged = dict(row.properties or {})
        merged.update(props)
        row.properties = merged
        db.flush()
        return row
    row = KgEntity(
        type_id=type_id,
        name=name.strip()[:256],
        description=description or "",
        properties=props,
        owner_id=user.id,
        created_by=user.id,
        scope="company",
    )
    db.add(row)
    db.flush()
    return row


def _reconcile_employs(
    db: Session,
    user: User,
    *,
    person_id: uuid.UUID,
    dept_entity_id: uuid.UUID | None,
    employs_id: uuid.UUID,
) -> None:
    """保留当前部门任职关系，移除该人员其它 employs 边。"""
    existing = db.scalars(
        select(KgRelation).where(
            KgRelation.owner_id == user.id,
            KgRelation.relation_type_id == employs_id,
            KgRelation.to_entity_id == person_id,
        )
    ).all()
    for rel in existing:
        if dept_entity_id and rel.from_entity_id == dept_entity_id:
            continue
        db.delete(rel)
    if dept_entity_id:
        _ensure_relation(
            db,
            user,
            relation_type_id=employs_id,
            from_id=dept_entity_id,
            to_id=person_id,
        )


def _ensure_relation(
    db: Session,
    user: User,
    *,
    relation_type_id: uuid.UUID,
    from_id: uuid.UUID,
    to_id: uuid.UUID,
) -> None:
    if from_id == to_id:
        return
    exists = db.scalar(
        select(KgRelation.id).where(
            KgRelation.owner_id == user.id,
            KgRelation.relation_type_id == relation_type_id,
            KgRelation.from_entity_id == from_id,
            KgRelation.to_entity_id == to_id,
        )
    )
    if exists:
        return
    db.add(
        KgRelation(
            relation_type_id=relation_type_id,
            from_entity_id=from_id,
            to_entity_id=to_id,
            owner_id=user.id,
            created_by=user.id,
        )
    )


def sync_platform_org_to_kg(db: Session, user: User) -> dict[str, int]:
    """Upsert 部门为 org 实体、用户为 person 实体，并写入组织关系。"""
    ensure_ontology_defaults(db)
    type_ids = _type_by_code(db)
    org_type_id = type_ids.get("org")
    person_type_id = type_ids.get("person")
    contains_id = _rel_type_id(db, "contains")
    employs_id = _rel_type_id(db, "employs")
    if not org_type_id or not person_type_id or not contains_id or not employs_id:
        return {"departments": 0, "users": 0, "relations": 0}

    dept_rows = list(
        db.scalars(select(Department).order_by(Department.sort_order, Department.name)).all()
    )
    dept_entity: dict[uuid.UUID, KgEntity] = {}
    for dept in dept_rows:
        dept_entity[dept.id] = _upsert_entity(
            db,
            user,
            type_id=org_type_id,
            name=dept.name,
            description="组织部门",
            prop_key=DEPT_ID_PROP,
            prop_value=str(dept.id),
        )

    rel_count = 0
    for dept in dept_rows:
        parent_ent = dept_entity.get(dept.id)
        if dept.parent_id and dept.parent_id in dept_entity and parent_ent:
            parent = dept_entity[dept.parent_id]
            child = dept_entity[dept.id]
            _ensure_relation(
                db,
                user,
                relation_type_id=contains_id,
                from_id=parent.id,
                to_id=child.id,
            )
            rel_count += 1

    user_rows = list(
        db.scalars(
            select(User).where(User.status == UserStatus.active.value)
        ).all()
    )
    for u in user_rows:
        label = (u.display_name or u.username or u.phone or "用户").strip()
        desc_parts = []
        if u.phone:
            desc_parts.append(f"手机 {u.phone}")
        if u.email:
            desc_parts.append(f"邮箱 {u.email}")
        if u.username:
            desc_parts.append(f"账号 {u.username}")
        person = _upsert_entity(
            db,
            user,
            type_id=person_type_id,
            name=label,
            description=" · ".join(desc_parts) if desc_parts else "平台用户",
            prop_key=USER_ID_PROP,
            prop_value=str(u.id),
            extra_props={
                "phone": u.phone or "",
                "email": u.email or "",
                "username": u.username or "",
            },
        )
        membership = db.scalar(
            select(UserDepartment).where(UserDepartment.user_id == u.id)
        )
        target_dept_id = (
            dept_entity[membership.dept_id].id
            if membership and membership.dept_id in dept_entity
            else None
        )
        _reconcile_employs(
            db,
            user,
            person_id=person.id,
            dept_entity_id=target_dept_id,
            employs_id=employs_id,
        )
        if target_dept_id:
            rel_count += 1

    db.flush()
    return {
        "departments": len(dept_rows),
        "users": len(user_rows),
        "relations": rel_count,
    }
