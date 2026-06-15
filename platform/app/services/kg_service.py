"""知识图谱：本体维护、实体/关系 CRUD 与子图查询。"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import bad_request, not_found
from app.models.kg import KgEntity, KgEntityType, KgRelation, KgRelationType
from app.models.org import User
from app.schemas.kg import (
    KgEntityIn,
    KgEntityOut,
    KgEntityTypeIn,
    KgEntityTypeOut,
    KgEntityTypeUpdate,
    KgEntityUpdate,
    KgGraphEdgeOut,
    KgGraphNodeOut,
    KgGraphOut,
    KgMetaOut,
    KgRelationIn,
    KgRelationOut,
    KgRelationTypeIn,
    KgRelationTypeOut,
    KgRelationTypeUpdate,
)

DEFAULT_ENTITY_TYPES: list[tuple[str, str, str, int]] = [
    ("org", "组织", "blue", 10),
    ("person", "人员", "green", 20),
    ("doc", "文档", "purple", 30),
    ("regulation", "法规/标准", "orange", 40),
    ("project", "项目", "pink", 50),
    ("metric", "指标", "yellow", 60),
]

DEFAULT_RELATION_TYPES: list[tuple[str, str, int]] = [
    ("contains", "包含", 10),
    ("employs", "任职", 20),
    ("references", "引用", 30),
    ("based_on", "依据", 40),
    ("responsible", "负责", 50),
    ("constrains", "约束", 60),
    ("produces", "产出", 70),
]


def ensure_ontology_defaults(db: Session) -> None:
    for code, label, color, sort_order in DEFAULT_ENTITY_TYPES:
        exists = db.scalar(select(KgEntityType.id).where(KgEntityType.code == code))
        if not exists:
            db.add(
                KgEntityType(
                    code=code,
                    label=label,
                    color=color,
                    sort_order=sort_order,
                )
            )
    for code, label, sort_order in DEFAULT_RELATION_TYPES:
        exists = db.scalar(select(KgRelationType.id).where(KgRelationType.code == code))
        if not exists:
            db.add(
                KgRelationType(
                    code=code,
                    label=label,
                    sort_order=sort_order,
                )
            )
    db.flush()


def _entity_counts(db: Session, owner_id: uuid.UUID) -> dict[uuid.UUID, int]:
    rows = db.execute(
        select(KgEntity.type_id, func.count())
        .where(KgEntity.owner_id == owner_id)
        .group_by(KgEntity.type_id)
    ).all()
    return {type_id: int(count) for type_id, count in rows}


def _relation_counts(db: Session, owner_id: uuid.UUID) -> dict[uuid.UUID, int]:
    rows = db.execute(
        select(KgRelation.relation_type_id, func.count())
        .where(KgRelation.owner_id == owner_id)
        .group_by(KgRelation.relation_type_id)
    ).all()
    return {type_id: int(count) for type_id, count in rows}


def seed_demo_graph(db: Session, user: User) -> None:
    """首次进入且无实体时写入示例子图。"""
    total = db.scalar(
        select(func.count()).select_from(KgEntity).where(KgEntity.owner_id == user.id)
    )
    if total and int(total) > 0:
        return

    ensure_ontology_defaults(db)
    type_by_code = {
        t.code: t
        for t in db.scalars(select(KgEntityType).order_by(KgEntityType.sort_order)).all()
    }
    rel_by_code = {
        t.code: t
        for t in db.scalars(select(KgRelationType).order_by(KgRelationType.sort_order)).all()
    }

    def add_entity(code: str, name: str, description: str = "") -> KgEntity:
        et = type_by_code[code]
        row = KgEntity(
            type_id=et.id,
            name=name,
            description=description,
            owner_id=user.id,
            created_by=user.id,
            scope="personal",
        )
        db.add(row)
        db.flush()
        return row

    org = add_entity("org", "示例公司")
    dept = add_entity("org", "研发部")
    person = add_entity("person", "张三")
    doc = add_entity("doc", "碳排放核算指南")
    reg = add_entity("regulation", "全国碳市场管理办法")
    proj = add_entity("project", "减排路径规划", "部门级减排路径项目")
    metric = add_entity("metric", "范围一排放量")

    def add_rel(code: str, from_id: uuid.UUID, to_id: uuid.UUID) -> None:
        rt = rel_by_code[code]
        db.add(
            KgRelation(
                relation_type_id=rt.id,
                from_entity_id=from_id,
                to_entity_id=to_id,
                owner_id=user.id,
                created_by=user.id,
            )
        )

    add_rel("contains", org.id, dept.id)
    add_rel("employs", dept.id, person.id)
    add_rel("responsible", person.id, proj.id)
    add_rel("references", proj.id, doc.id)
    add_rel("based_on", doc.id, reg.id)
    add_rel("produces", proj.id, metric.id)
    add_rel("constrains", reg.id, metric.id)
    db.flush()


def get_meta(db: Session, user: User) -> KgMetaOut:
    ensure_ontology_defaults(db)
    seed_demo_graph(db, user)
    db.commit()

    entity_counts = _entity_counts(db, user.id)
    relation_counts = _relation_counts(db, user.id)

    entity_types = [
        KgEntityTypeOut(
            id=t.id,
            code=t.code,
            label=t.label,
            color=t.color,
            description=t.description,
            sort_order=t.sort_order,
            entity_count=entity_counts.get(t.id, 0),
        )
        for t in db.scalars(
            select(KgEntityType).order_by(KgEntityType.sort_order, KgEntityType.code)
        ).all()
    ]
    relation_types = [
        KgRelationTypeOut(
            id=t.id,
            code=t.code,
            label=t.label,
            description=t.description,
            sort_order=t.sort_order,
            relation_count=relation_counts.get(t.id, 0),
        )
        for t in db.scalars(
            select(KgRelationType).order_by(KgRelationType.sort_order, KgRelationType.code)
        ).all()
    ]

    entity_total = db.scalar(
        select(func.count()).select_from(KgEntity).where(KgEntity.owner_id == user.id)
    )
    relation_total = db.scalar(
        select(func.count()).select_from(KgRelation).where(KgRelation.owner_id == user.id)
    )

    return KgMetaOut(
        entity_types=entity_types,
        relation_types=relation_types,
        entity_total=int(entity_total or 0),
        relation_total=int(relation_total or 0),
    )


def _entity_out(db: Session, row: KgEntity) -> KgEntityOut:
    et = db.get(KgEntityType, row.type_id)
    if not et:
        raise not_found("实体类型不存在")
    return KgEntityOut(
        id=row.id,
        type_id=row.type_id,
        type_code=et.code,
        type_label=et.label,
        type_color=et.color,
        name=row.name,
        description=row.description,
        properties=dict(row.properties or {}),
        scope=row.scope,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_entities(
    db: Session,
    user: User,
    *,
    type_id: uuid.UUID | None = None,
    q: str | None = None,
) -> list[KgEntityOut]:
    stmt = select(KgEntity).where(KgEntity.owner_id == user.id)
    if type_id:
        stmt = stmt.where(KgEntity.type_id == type_id)
    if q and q.strip():
        kw = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(KgEntity.name.ilike(kw), KgEntity.description.ilike(kw))
        )
    rows = db.scalars(stmt.order_by(KgEntity.updated_at.desc(), KgEntity.name)).all()
    return [_entity_out(db, row) for row in rows]


def get_entity(db: Session, user: User, entity_id: uuid.UUID) -> KgEntityOut:
    row = db.scalar(
        select(KgEntity).where(
            KgEntity.id == entity_id,
            KgEntity.owner_id == user.id,
        )
    )
    if not row:
        raise not_found("实体不存在")
    return _entity_out(db, row)


def create_entity(db: Session, user: User, body: KgEntityIn) -> KgEntityOut:
    et = db.get(KgEntityType, body.type_id)
    if not et:
        raise bad_request("实体类型不存在")
    row = KgEntity(
        type_id=body.type_id,
        name=body.name.strip(),
        description=body.description or "",
        properties=body.properties or {},
        owner_id=user.id,
        created_by=user.id,
        scope="personal",
    )
    db.add(row)
    db.flush()
    db.commit()
    db.refresh(row)
    return _entity_out(db, row)


def update_entity(
    db: Session,
    user: User,
    entity_id: uuid.UUID,
    body: KgEntityUpdate,
) -> KgEntityOut:
    row = db.scalar(
        select(KgEntity).where(
            KgEntity.id == entity_id,
            KgEntity.owner_id == user.id,
        )
    )
    if not row:
        raise not_found("实体不存在")
    if body.type_id is not None:
        et = db.get(KgEntityType, body.type_id)
        if not et:
            raise bad_request("实体类型不存在")
        row.type_id = body.type_id
    if body.name is not None:
        row.name = body.name.strip()
    if body.description is not None:
        row.description = body.description
    if body.properties is not None:
        row.properties = body.properties
    db.commit()
    db.refresh(row)
    return _entity_out(db, row)


def delete_entity(db: Session, user: User, entity_id: uuid.UUID) -> None:
    row = db.scalar(
        select(KgEntity).where(
            KgEntity.id == entity_id,
            KgEntity.owner_id == user.id,
        )
    )
    if not row:
        raise not_found("实体不存在")
    db.delete(row)
    db.commit()


def _relation_out(db: Session, row: KgRelation) -> KgRelationOut:
    rt = db.get(KgRelationType, row.relation_type_id)
    from_ent = db.get(KgEntity, row.from_entity_id)
    to_ent = db.get(KgEntity, row.to_entity_id)
    if not rt or not from_ent or not to_ent:
        raise not_found("关系数据不完整")
    return KgRelationOut(
        id=row.id,
        relation_type_id=row.relation_type_id,
        relation_type_code=rt.code,
        relation_type_label=rt.label,
        from_entity_id=row.from_entity_id,
        to_entity_id=row.to_entity_id,
        from_name=from_ent.name,
        to_name=to_ent.name,
        description=row.description,
        created_at=row.created_at,
    )


def list_relations(
    db: Session,
    user: User,
    *,
    entity_id: uuid.UUID | None = None,
) -> list[KgRelationOut]:
    stmt = select(KgRelation).where(KgRelation.owner_id == user.id)
    if entity_id:
        stmt = stmt.where(
            or_(
                KgRelation.from_entity_id == entity_id,
                KgRelation.to_entity_id == entity_id,
            )
        )
    rows = db.scalars(stmt.order_by(KgRelation.created_at.desc())).all()
    return [_relation_out(db, row) for row in rows]


def create_relation(db: Session, user: User, body: KgRelationIn) -> KgRelationOut:
    if body.from_entity_id == body.to_entity_id:
        raise bad_request("关系的起点与终点不能相同")
    rt = db.get(KgRelationType, body.relation_type_id)
    if not rt:
        raise bad_request("关系类型不存在")
    from_ent = db.scalar(
        select(KgEntity).where(
            KgEntity.id == body.from_entity_id,
            KgEntity.owner_id == user.id,
        )
    )
    to_ent = db.scalar(
        select(KgEntity).where(
            KgEntity.id == body.to_entity_id,
            KgEntity.owner_id == user.id,
        )
    )
    if not from_ent or not to_ent:
        raise bad_request("实体不存在或无权访问")

    dup = db.scalar(
        select(KgRelation).where(
            KgRelation.owner_id == user.id,
            KgRelation.relation_type_id == body.relation_type_id,
            KgRelation.from_entity_id == body.from_entity_id,
            KgRelation.to_entity_id == body.to_entity_id,
        )
    )
    if dup:
        raise bad_request("相同关系已存在")

    row = KgRelation(
        relation_type_id=body.relation_type_id,
        from_entity_id=body.from_entity_id,
        to_entity_id=body.to_entity_id,
        description=body.description or "",
        owner_id=user.id,
        created_by=user.id,
    )
    db.add(row)
    db.flush()
    db.commit()
    db.refresh(row)
    return _relation_out(db, row)


def delete_relation(db: Session, user: User, relation_id: uuid.UUID) -> None:
    row = db.scalar(
        select(KgRelation).where(
            KgRelation.id == relation_id,
            KgRelation.owner_id == user.id,
        )
    )
    if not row:
        raise not_found("关系不存在")
    db.delete(row)
    db.commit()


def create_entity_type(db: Session, body: KgEntityTypeIn) -> KgEntityTypeOut:
    code = body.code.strip()
    if db.scalar(select(KgEntityType.id).where(KgEntityType.code == code)):
        raise bad_request("实体类型 code 已存在")
    row = KgEntityType(
        code=code,
        label=body.label.strip(),
        color=body.color or "blue",
        description=body.description or "",
        sort_order=body.sort_order,
    )
    db.add(row)
    db.flush()
    db.commit()
    db.refresh(row)
    return KgEntityTypeOut(
        id=row.id,
        code=row.code,
        label=row.label,
        color=row.color,
        description=row.description,
        sort_order=row.sort_order,
        entity_count=0,
    )


def update_entity_type(
    db: Session,
    type_id: uuid.UUID,
    body: KgEntityTypeUpdate,
) -> KgEntityTypeOut:
    row = db.get(KgEntityType, type_id)
    if not row:
        raise not_found("实体类型不存在")
    if body.label is not None:
        row.label = body.label.strip()
    if body.color is not None:
        row.color = body.color
    if body.description is not None:
        row.description = body.description
    if body.sort_order is not None:
        row.sort_order = body.sort_order
    db.commit()
    db.refresh(row)
    return KgEntityTypeOut(
        id=row.id,
        code=row.code,
        label=row.label,
        color=row.color,
        description=row.description,
        sort_order=row.sort_order,
        entity_count=0,
    )


def delete_entity_type(db: Session, type_id: uuid.UUID) -> None:
    row = db.get(KgEntityType, type_id)
    if not row:
        raise not_found("实体类型不存在")
    in_use = db.scalar(
        select(func.count()).select_from(KgEntity).where(KgEntity.type_id == type_id)
    )
    if int(in_use or 0) > 0:
        raise bad_request("该类型下仍有实体，无法删除")
    db.delete(row)
    db.commit()


def create_relation_type(db: Session, body: KgRelationTypeIn) -> KgRelationTypeOut:
    code = body.code.strip()
    if db.scalar(select(KgRelationType.id).where(KgRelationType.code == code)):
        raise bad_request("关系类型 code 已存在")
    row = KgRelationType(
        code=code,
        label=body.label.strip(),
        description=body.description or "",
        sort_order=body.sort_order,
    )
    db.add(row)
    db.flush()
    db.commit()
    db.refresh(row)
    return KgRelationTypeOut(
        id=row.id,
        code=row.code,
        label=row.label,
        description=row.description,
        sort_order=row.sort_order,
        relation_count=0,
    )


def update_relation_type(
    db: Session,
    type_id: uuid.UUID,
    body: KgRelationTypeUpdate,
) -> KgRelationTypeOut:
    row = db.get(KgRelationType, type_id)
    if not row:
        raise not_found("关系类型不存在")
    if body.label is not None:
        row.label = body.label.strip()
    if body.description is not None:
        row.description = body.description
    if body.sort_order is not None:
        row.sort_order = body.sort_order
    db.commit()
    db.refresh(row)
    return KgRelationTypeOut(
        id=row.id,
        code=row.code,
        label=row.label,
        description=row.description,
        sort_order=row.sort_order,
        relation_count=0,
    )


def delete_relation_type(db: Session, type_id: uuid.UUID) -> None:
    row = db.get(KgRelationType, type_id)
    if not row:
        raise not_found("关系类型不存在")
    in_use = db.scalar(
        select(func.count()).select_from(KgRelation).where(
            KgRelation.relation_type_id == type_id
        )
    )
    if int(in_use or 0) > 0:
        raise bad_request("该关系类型仍在使用，无法删除")
    db.delete(row)
    db.commit()


def get_graph(
    db: Session,
    user: User,
    *,
    focus_entity_id: uuid.UUID | None = None,
    depth: int = 1,
) -> KgGraphOut:
    depth = max(1, min(depth, 3))
    entity_ids: set[uuid.UUID] = set()
    if focus_entity_id:
        entity_ids.add(focus_entity_id)
        frontier = {focus_entity_id}
        for _ in range(depth):
            if not frontier:
                break
            rels = db.scalars(
                select(KgRelation).where(
                    KgRelation.owner_id == user.id,
                    or_(
                        KgRelation.from_entity_id.in_(frontier),
                        KgRelation.to_entity_id.in_(frontier),
                    ),
                )
            ).all()
            next_frontier: set[uuid.UUID] = set()
            for rel in rels:
                entity_ids.add(rel.from_entity_id)
                entity_ids.add(rel.to_entity_id)
                next_frontier.add(rel.from_entity_id)
                next_frontier.add(rel.to_entity_id)
            frontier = next_frontier
    else:
        rows = db.scalars(
            select(KgEntity.id)
            .where(KgEntity.owner_id == user.id)
            .order_by(KgEntity.updated_at.desc())
            .limit(50)
        ).all()
        entity_ids = set(rows)

    if not entity_ids:
        return KgGraphOut(nodes=[], edges=[], focus_entity_id=focus_entity_id)

    entities = db.scalars(
        select(KgEntity).where(
            KgEntity.owner_id == user.id,
            KgEntity.id.in_(entity_ids),
        )
    ).all()
    type_map = {
        t.id: t
        for t in db.scalars(select(KgEntityType)).all()
    }

    nodes = []
    for ent in entities:
        et = type_map.get(ent.type_id)
        if not et:
            continue
        nodes.append(
            KgGraphNodeOut(
                id=ent.id,
                name=ent.name,
                type_code=et.code,
                type_label=et.label,
                type_color=et.color,
            )
        )

    rel_rows = db.scalars(
        select(KgRelation).where(
            KgRelation.owner_id == user.id,
            KgRelation.from_entity_id.in_(entity_ids),
            KgRelation.to_entity_id.in_(entity_ids),
        )
    ).all()
    rel_type_map = {t.id: t for t in db.scalars(select(KgRelationType)).all()}
    edges = []
    for rel in rel_rows:
        rt = rel_type_map.get(rel.relation_type_id)
        if not rt:
            continue
        edges.append(
            KgGraphEdgeOut(
                id=rel.id,
                relation_type_code=rt.code,
                relation_type_label=rt.label,
                from_entity_id=rel.from_entity_id,
                to_entity_id=rel.to_entity_id,
            )
        )

    return KgGraphOut(
        nodes=nodes,
        edges=edges,
        focus_entity_id=focus_entity_id,
    )


@dataclass
class KgQaContext:
    context_text: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    matched_entity_ids: list[uuid.UUID] = field(default_factory=list)
    entity_count: int = 0
    relation_count: int = 0


def _question_entity_match_score(question: str, name: str, description: str = "") -> float:
    q = (question or "").strip()
    name = (name or "").strip()
    if not q or not name:
        return 0.0
    if name in q:
        return 100.0 + len(name)
    q_lower = q.lower()
    name_lower = name.lower()
    if name_lower in q_lower:
        return 100.0 + len(name)
    score = 0.0
    for token in re.split(r"[\s,，、；;：:？?！!（）()\"'“”]+", name):
        token = token.strip()
        if len(token) >= 2 and token in q:
            score = max(score, 20.0 + len(token))
    desc = (description or "").strip()
    if desc and len(desc) >= 4:
        for chunk in (desc[:24], desc[:16]):
            if len(chunk) >= 4 and chunk in q:
                score = max(score, 8.0 + len(chunk))
                break
    return score


def match_entities_in_question(
    db: Session,
    user: User,
    question: str,
    *,
    limit: int = 5,
) -> list[tuple[KgEntity, float]]:
    """从问题文本中匹配用户图谱实体（名称/描述子串）。"""
    rows = db.scalars(
        select(KgEntity)
        .where(KgEntity.owner_id == user.id)
        .order_by(KgEntity.updated_at.desc(), KgEntity.name)
    ).all()
    scored: list[tuple[KgEntity, float]] = []
    for ent in rows:
        score = _question_entity_match_score(question, ent.name, ent.description)
        if score > 0:
            scored.append((ent, score))
    scored.sort(key=lambda item: (-item[1], -len(item[0].name), item[0].name))
    return scored[:limit]


def _expand_entity_ids_from_seeds(
    db: Session,
    user: User,
    seed_ids: set[uuid.UUID],
    depth: int,
) -> set[uuid.UUID]:
    entity_ids = set(seed_ids)
    frontier = set(seed_ids)
    depth = max(1, min(depth, 3))
    for _ in range(depth):
        if not frontier:
            break
        rels = db.scalars(
            select(KgRelation).where(
                KgRelation.owner_id == user.id,
                or_(
                    KgRelation.from_entity_id.in_(frontier),
                    KgRelation.to_entity_id.in_(frontier),
                ),
            )
        ).all()
        next_frontier: set[uuid.UUID] = set()
        for rel in rels:
            entity_ids.add(rel.from_entity_id)
            entity_ids.add(rel.to_entity_id)
            next_frontier.add(rel.from_entity_id)
            next_frontier.add(rel.to_entity_id)
        frontier = next_frontier
    return entity_ids


def build_kg_qa_context(
    *,
    entities: list[KgEntity],
    relations: list[KgRelation],
    type_map: dict[uuid.UUID, KgEntityType],
    rel_type_map: dict[uuid.UUID, KgRelationType],
    matched_ids: set[uuid.UUID],
) -> KgQaContext:
    name_by_id = {ent.id: ent.name for ent in entities}
    sorted_ents = sorted(
        entities,
        key=lambda ent: (0 if ent.id in matched_ids else 1, ent.name),
    )

    citations: list[dict[str, Any]] = []
    blocks: list[str] = []
    for index, ent in enumerate(sorted_ents, start=1):
        et = type_map.get(ent.type_id)
        type_label = et.label if et else "实体"
        rel_lines: list[str] = []
        for rel in relations:
            rt = rel_type_map.get(rel.relation_type_id)
            if not rt:
                continue
            if rel.from_entity_id == ent.id:
                to_name = name_by_id.get(rel.to_entity_id, "?")
                rel_lines.append(f"- {ent.name} —[{rt.label}]→ {to_name}")
            elif rel.to_entity_id == ent.id:
                from_name = name_by_id.get(rel.from_entity_id, "?")
                rel_lines.append(f"- {from_name} —[{rt.label}]→ {ent.name}")

        desc = (ent.description or "").strip()
        body_parts: list[str] = []
        if desc:
            body_parts.append(desc)
        if rel_lines:
            body_parts.append("关联：\n" + "\n".join(rel_lines))
        snippet = "\n".join(body_parts) if body_parts else "（无描述与关联）"
        title = f"{type_label} · {ent.name}"
        blocks.append(f"[{index}] {title}\n{snippet}")
        citations.append(
            {
                "index": index,
                "title": title,
                "snippet": snippet[:2000],
                "score": 1.0 if ent.id in matched_ids else None,
                "source": "kg",
                "entity_id": str(ent.id),
                "type_label": type_label,
            }
        )

    return KgQaContext(
        context_text="【知识图谱实体与关系】\n" + "\n\n".join(blocks),
        citations=citations,
        matched_entity_ids=sorted(matched_ids, key=str),
        entity_count=len(entities),
        relation_count=len(relations),
    )


def retrieve_kg_context_for_question(
    db: Session,
    user: User,
    question: str,
    *,
    depth: int = 2,
    match_limit: int = 5,
) -> KgQaContext | None:
    """解析问题中的实体 mention，扩展子图并格式化为问答上下文。"""
    ensure_ontology_defaults(db)
    seed_demo_graph(db, user)
    db.flush()

    matches = match_entities_in_question(db, user, question, limit=match_limit)
    if not matches:
        return None

    seed_ids = {ent.id for ent, _ in matches}
    entity_ids = _expand_entity_ids_from_seeds(db, user, seed_ids, depth=depth)
    entities = db.scalars(
        select(KgEntity).where(
            KgEntity.owner_id == user.id,
            KgEntity.id.in_(entity_ids),
        )
    ).all()
    relations = db.scalars(
        select(KgRelation).where(
            KgRelation.owner_id == user.id,
            KgRelation.from_entity_id.in_(entity_ids),
            KgRelation.to_entity_id.in_(entity_ids),
        )
    ).all()
    type_map = {t.id: t for t in db.scalars(select(KgEntityType)).all()}
    rel_type_map = {t.id: t for t in db.scalars(select(KgRelationType)).all()}
    return build_kg_qa_context(
        entities=list(entities),
        relations=list(relations),
        type_map=type_map,
        rel_type_map=rel_type_map,
        matched_ids=seed_ids,
    )
