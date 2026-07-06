"""将平台用户、部门组织树与智能体能力拓扑同步到当前用户的知识图谱实体。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.kg import KgEntity, KgRelation, KgRelationType
from app.models.org import Department, User, UserDepartment, UserStatus
from app.services.kg_service import ensure_ontology_defaults

USER_ID_PROP = "platform_user_id"
DEPT_ID_PROP = "platform_department_id"
AGENT_ID_PROP = "platform_agent_id"
TOOL_NAME_PROP = "platform_tool_name"
SKILL_NAME_PROP = "platform_skill_name"


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


def _reconcile_outgoing_relations(
    db: Session,
    user: User,
    *,
    from_id: uuid.UUID,
    relation_type_id: uuid.UUID,
    allowed_to_ids: set[uuid.UUID],
) -> None:
    """移除此节点上不在允许集合内的出边。"""
    existing = db.scalars(
        select(KgRelation).where(
            KgRelation.owner_id == user.id,
            KgRelation.relation_type_id == relation_type_id,
            KgRelation.from_entity_id == from_id,
        )
    ).all()
    for rel in existing:
        if rel.to_entity_id not in allowed_to_ids:
            db.delete(rel)


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


def _agent_bound_skill_names(db: Session, agent_id: str) -> list[str]:
    """图谱同步用：返回智能体配置绑定的 Skill 名（含 catalog 未展示的项）。"""
    from app.core.agent_profiles import get_agent_profile
    from app.services.agent_profile_service import _binding_map, _effective_skill_names
    from app.skills.catalog import list_all_skill_definitions

    defn = get_agent_profile(agent_id)
    if not defn:
        return []
    binding = _binding_map(db).get(defn.id)
    if binding is not None and not binding.enabled:
        return []
    names = _effective_skill_names(defn, binding)
    known = {
        skill.name
        for skill in list_all_skill_definitions(
            db, admin_view=True, include_disabled=True, catalog_only=False
        )
    }
    return [name for name in names if name in known]


def sync_platform_agents_to_kg(db: Session, user: User) -> dict[str, int]:
    """Upsert 平台智能体、原子工具、Skill 及 has_tool / has_skill / orchestrates 关系。"""
    from app.core.agent_profiles import AGENT_PROFILES
    from app.services.agent_profile_service import (
        is_agent_enabled,
        resolve_agent_internal_atomic_tools,
    )
    from app.services.agent_tool_registry import list_agent_tools
    from app.skills.catalog import list_all_skill_definitions

    ensure_ontology_defaults(db)
    type_ids = _type_by_code(db)
    agent_type_id = type_ids.get("agent")
    tool_type_id = type_ids.get("tool")
    skill_type_id = type_ids.get("skill")
    has_tool_id = _rel_type_id(db, "has_tool")
    has_skill_id = _rel_type_id(db, "has_skill")
    orchestrates_id = _rel_type_id(db, "orchestrates")
    if (
        not agent_type_id
        or not tool_type_id
        or not skill_type_id
        or not has_tool_id
        or not has_skill_id
        or not orchestrates_id
    ):
        return {"agents": 0, "tools": 0, "skills": 0, "relations": 0}

    skill_defs = list_all_skill_definitions(
        db, admin_view=True, include_disabled=True, catalog_only=False
    )

    tool_entities: dict[str, KgEntity] = {}
    for tool in list_agent_tools(db, user=None):
        category = tool.category.value if hasattr(tool.category, "value") else str(tool.category)
        tool_entities[tool.name] = _upsert_entity(
            db,
            user,
            type_id=tool_type_id,
            name=tool.name,
            description=(tool.description or "").strip() or "平台原子工具",
            prop_key=TOOL_NAME_PROP,
            prop_value=tool.name,
            extra_props={
                "category": category,
                "available": bool(tool.available),
            },
        )

    skill_entities: dict[str, KgEntity] = {}
    for skill in skill_defs:
        extra_props: dict[str, str] = {
            "source": skill.source.value,
            "readiness": skill.readiness.value,
            "slug": skill.name,
        }
        if skill.skill_id:
            extra_props["skill_id"] = str(skill.skill_id)
        skill_entities[skill.name] = _upsert_entity(
            db,
            user,
            type_id=skill_type_id,
            name=(skill.title or skill.name).strip()[:256],
            description=(skill.description or "").strip() or "平台 Skill",
            prop_key=SKILL_NAME_PROP,
            prop_value=skill.name,
            extra_props=extra_props,
        )

    rel_count = 0
    for defn in AGENT_PROFILES:
        enabled = is_agent_enabled(db, defn.id)
        agent_ent = _upsert_entity(
            db,
            user,
            type_id=agent_type_id,
            name=defn.title,
            description=defn.description,
            prop_key=AGENT_ID_PROP,
            prop_value=defn.id,
            extra_props={
                "agent_id": defn.id,
                "enabled": enabled,
                "skills_configurable": defn.skills_configurable,
            },
        )

        tool_names = resolve_agent_internal_atomic_tools(db, defn.id)
        allowed_tool_ids = {
            tool_entities[name].id for name in tool_names if name in tool_entities
        }
        _reconcile_outgoing_relations(
            db,
            user,
            from_id=agent_ent.id,
            relation_type_id=has_tool_id,
            allowed_to_ids=allowed_tool_ids,
        )
        for tool_id in allowed_tool_ids:
            _ensure_relation(
                db,
                user,
                relation_type_id=has_tool_id,
                from_id=agent_ent.id,
                to_id=tool_id,
            )
            rel_count += 1

        skill_names = _agent_bound_skill_names(db, defn.id)
        allowed_skill_ids = {
            skill_entities[name].id for name in skill_names if name in skill_entities
        }
        _reconcile_outgoing_relations(
            db,
            user,
            from_id=agent_ent.id,
            relation_type_id=has_skill_id,
            allowed_to_ids=allowed_skill_ids,
        )
        for skill_id in allowed_skill_ids:
            _ensure_relation(
                db,
                user,
                relation_type_id=has_skill_id,
                from_id=agent_ent.id,
                to_id=skill_id,
            )
            rel_count += 1

    for skill in skill_defs:
        skill_ent = skill_entities.get(skill.name)
        if not skill_ent:
            continue
        allowed_tool_ids = {
            tool_entities[name].id
            for name in skill.orchestrated_tools
            if name in tool_entities
        }
        _reconcile_outgoing_relations(
            db,
            user,
            from_id=skill_ent.id,
            relation_type_id=orchestrates_id,
            allowed_to_ids=allowed_tool_ids,
        )
        for tool_id in allowed_tool_ids:
            _ensure_relation(
                db,
                user,
                relation_type_id=orchestrates_id,
                from_id=skill_ent.id,
                to_id=tool_id,
            )
            rel_count += 1

    db.flush()
    return {
        "agents": len(AGENT_PROFILES),
        "tools": len(tool_entities),
        "skills": len(skill_entities),
        "relations": rel_count,
    }
