"""问数字段映射：自动发现 + 持久化 + 供 FieldMapper 读取。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.semantic.defaults import DEFAULT_ENTITY_TYPES
from app.semantic.ontology.sql_registry import (
    allowed_columns_for_table,
    executable_sql_tables,
    get_sql_binding_registry,
)
from app.models.semantic_field_binding import SemanticFieldBinding

logger = logging.getLogger(__name__)

# 概念 → 候选表名
_CONCEPT_TABLE_ALIASES: dict[str, tuple[str, ...]] = {
    "person": ("users", "user", "persons", "people"),
    "org": ("departments", "department", "orgs", "organizations"),
    "doc": ("documents", "document", "docs"),
    "agent": ("agent_profiles", "agents"),
    "tool": ("tools",),
    "skill": ("agent_skills", "skills"),
}

# 属性 → 候选列名
_PROP_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "phone": ("phone", "mobile", "tel", "telephone", "cellphone"),
    "email": ("email", "mail", "e_mail"),
    "full_name": ("name", "full_name", "title", "display_name"),
    "username": ("username", "user_name", "login"),
    "department": ("department_name", "dept_name", "department"),
    "document_id": ("id", "document_id"),
}

_IDENTITY_PROPS = frozenset({"name", "username", "title", "code"})


@dataclass
class BindingRow:
    concept: str
    property_key: str
    source: str
    table_name: str = ""
    column_name: str = ""
    join_template: str = ""
    notes: str = ""
    confidence: float = 1.0
    origin: str = "auto"
    enabled: bool = True
    status: str = "active"
    id: str = ""


def list_bindings(db: Session, *, enabled_only: bool = False) -> list[BindingRow]:
    """读取映射；表不存在或查询失败时返回空列表（映射非本体必需）。"""
    try:
        q = select(SemanticFieldBinding).order_by(
            SemanticFieldBinding.concept, SemanticFieldBinding.property_key
        )
        if enabled_only:
            q = q.where(
                SemanticFieldBinding.enabled.is_(True),
                SemanticFieldBinding.status == "active",
            )
        rows = db.scalars(q).all()
        return [_to_row(r) for r in rows]
    except Exception as exc:
        logger.warning("list semantic_field_bindings failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return []


def _to_row(r: SemanticFieldBinding) -> BindingRow:
    return BindingRow(
        id=str(r.id),
        concept=r.concept,
        property_key=r.property_key,
        source=r.source,
        table_name=r.table_name or "",
        column_name=r.column_name or "",
        join_template=r.join_template or "",
        notes=r.notes or "",
        confidence=float(r.confidence or 0),
        origin=r.origin or "auto",
        enabled=bool(r.enabled),
        status=r.status or "active",
    )


def _introspect_columns(db: Session) -> dict[str, set[str]]:
    """白名单表内实际存在的列。"""
    out: dict[str, set[str]] = {}
    try:
        insp = inspect(db.get_bind())
    except Exception as exc:
        logger.warning("schema introspect failed: %s", exc)
        return {t: set(cols) for t, cols in get_sql_binding_registry().table_columns.items()}
    for table in executable_sql_tables():
        allowed = allowed_columns_for_table(table)
        try:
            cols = {c["name"] for c in insp.get_columns(table)}
        except Exception:
            cols = set(allowed)
        out[table] = cols & set(allowed) if allowed else cols
    return out


def _concept_props_from_ontology() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for et in DEFAULT_ENTITY_TYPES:
        code = str(et.get("code") or "")
        schema = et.get("property_schema") or {}
        if not code or not isinstance(schema, dict):
            continue
        props = [str(k) for k in schema.keys()]
        # department 通过 join 绑定，未必在 property_schema
        if code == "person" and "department" not in props:
            props.append("department")
        result[code] = props
    return result


def discover_bindings(db: Session) -> list[BindingRow]:
    """根据本体属性 + 库表白名单自动发现映射候选。"""
    cols_by_table = _introspect_columns(db)
    concept_props = _concept_props_from_ontology()
    found: list[BindingRow] = []
    seen: set[tuple[str, str]] = set()
    reg = get_sql_binding_registry()

    # 1) 注册制 join（确定性高）
    for (concept, prop), (template_id, notes) in reg.sql_join_bindings.items():
        if template_id not in reg.join_template_columns:
            continue
        key = (concept, prop)
        if key in seen:
            continue
        seen.add(key)
        found.append(
            BindingRow(
                concept=concept,
                property_key=prop,
                source="sql",
                join_template=template_id,
                notes=notes,
                confidence=0.95,
                origin="auto",
                enabled=True,
                status="active",
            )
        )

    # 2) 列级对齐
    for concept, props in concept_props.items():
        tables = [
            t
            for t in _CONCEPT_TABLE_ALIASES.get(concept, ())
            if t in cols_by_table
        ]
        if not tables and concept in ("person", "org", "doc"):
            # 回退：任意白名单表名包含概念别名
            for t in cols_by_table:
                if any(a in t for a in _CONCEPT_TABLE_ALIASES.get(concept, (concept,))):
                    tables.append(t)
        for prop in props:
            if (concept, prop) in seen:
                continue
            if prop in _IDENTITY_PROPS:
                continue  # 关键标识不靠 SQL 问数映射
            col_aliases = _PROP_COLUMN_ALIASES.get(prop, (prop,))
            best: BindingRow | None = None
            for table in tables:
                available = cols_by_table.get(table) or set()
                for alias in col_aliases:
                    if alias in available:
                        conf = 0.98 if alias == prop else 0.85
                        cand = BindingRow(
                            concept=concept,
                            property_key=prop,
                            source="sql",
                            table_name=table,
                            column_name=alias,
                            notes=f"自动映射 {concept}.{prop} → {table}.{alias}",
                            confidence=conf,
                            origin="auto",
                            enabled=True,
                            status="active" if conf >= 0.9 else "pending",
                        )
                        if best is None or cand.confidence > best.confidence:
                            best = cand
            if best:
                seen.add((concept, prop))
                found.append(best)

    return found


def upsert_discovered(db: Session, rows: list[BindingRow] | None = None) -> dict[str, int]:
    """将发现结果写入库：不覆盖 origin=manual 的启用行。"""
    candidates = rows if rows is not None else discover_bindings(db)
    created = updated = skipped = 0
    for cand in candidates:
        existing = db.scalar(
            select(SemanticFieldBinding).where(
                SemanticFieldBinding.concept == cand.concept,
                SemanticFieldBinding.property_key == cand.property_key,
                SemanticFieldBinding.source == cand.source,
            )
        )
        if existing:
            if existing.origin == "manual" and existing.enabled:
                skipped += 1
                continue
            existing.table_name = cand.table_name
            existing.column_name = cand.column_name
            existing.join_template = cand.join_template
            existing.notes = cand.notes
            existing.confidence = cand.confidence
            existing.origin = cand.origin
            existing.status = cand.status
            existing.enabled = cand.enabled
            updated += 1
        else:
            db.add(
                SemanticFieldBinding(
                    concept=cand.concept,
                    property_key=cand.property_key,
                    source=cand.source,
                    table_name=cand.table_name,
                    column_name=cand.column_name,
                    join_template=cand.join_template,
                    notes=cand.notes,
                    confidence=cand.confidence,
                    origin=cand.origin,
                    enabled=cand.enabled,
                    status=cand.status,
                )
            )
            created += 1
    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped, "total": len(candidates)}


def ensure_bindings_populated(db: Session) -> None:
    """尽力确保映射表可用；失败则静默跳过（映射非本体必需）。"""
    from app.schema_migrate import ensure_semantic_field_binding_schema

    try:
        ensure_semantic_field_binding_schema(db.get_bind())
    except Exception as exc:
        logger.warning("ensure semantic_field_bindings schema failed: %s", exc)
        return
    try:
        n = db.scalar(select(SemanticFieldBinding.id).limit(1))
    except Exception as exc:
        logger.warning("read semantic_field_bindings failed: %s", exc)
        db.rollback()
        return
    if n is None:
        try:
            upsert_discovered(db)
        except Exception as exc:
            logger.warning("auto discover field bindings skipped: %s", exc)
            db.rollback()


def load_sql_maps(
    db: Session | None,
) -> tuple[
    dict[tuple[str, str], tuple[str, str, str]],
    dict[tuple[str, str], tuple[str, str]],
]:
    """供 FieldMapper 使用的 sql / join 字典。db 为空时回退注册表种子。"""
    seeds = get_sql_binding_registry()
    seed_sql = dict(seeds.sql_bindings)
    seed_joins = dict(seeds.sql_join_bindings)

    if db is None:
        return seed_sql, seed_joins
    try:
        ensure_bindings_populated(db)
        rows = list_bindings(db, enabled_only=True)
    except Exception as exc:
        logger.warning("load semantic bindings failed, fallback seeds: %s", exc)
        return seed_sql, seed_joins

    sql: dict[tuple[str, str], tuple[str, str, str]] = {}
    joins: dict[tuple[str, str], tuple[str, str]] = {}
    for r in rows:
        if r.join_template:
            joins[(r.concept, r.property_key)] = (r.join_template, r.notes)
        elif r.table_name and r.column_name:
            sql[(r.concept, r.property_key)] = (
                r.table_name,
                r.column_name,
                r.notes or "问数映射",
            )
    if not sql and not joins:
        return seed_sql, seed_joins
    merged_sql = dict(seed_sql)
    merged_sql.update(sql)
    merged_joins = dict(seed_joins)
    merged_joins.update(joins)
    return merged_sql, merged_joins


def field_mapper_from_db(db: Session | None) -> "FieldMapper":
    """从 DB（或注册表种子）构造 FieldMapper。"""
    from app.semantic.ontology.field_mapper import FieldMapper

    sql, joins = load_sql_maps(db)
    return FieldMapper(sql_bindings=sql, sql_join_bindings=joins)


def upsert_binding_manual(
    db: Session,
    *,
    concept: str,
    property_key: str,
    source: str = "sql",
    table_name: str = "",
    column_name: str = "",
    join_template: str = "",
    notes: str = "",
    enabled: bool = True,
    status: str = "active",
) -> BindingRow:
    concept = (concept or "").strip()
    property_key = (property_key or "").strip()
    source = (source or "sql").strip() or "sql"
    existing = db.scalar(
        select(SemanticFieldBinding).where(
            SemanticFieldBinding.concept == concept,
            SemanticFieldBinding.property_key == property_key,
            SemanticFieldBinding.source == source,
        )
    )
    if existing:
        existing.table_name = table_name or ""
        existing.column_name = column_name or ""
        existing.join_template = join_template or ""
        existing.notes = notes or existing.notes
        existing.enabled = enabled
        existing.status = status
        existing.origin = "manual"
        existing.confidence = 1.0
        db.commit()
        db.refresh(existing)
        return _to_row(existing)
    row = SemanticFieldBinding(
        concept=concept,
        property_key=property_key,
        source=source,
        table_name=table_name or "",
        column_name=column_name or "",
        join_template=join_template or "",
        notes=notes or "手动映射",
        confidence=1.0,
        origin="manual",
        enabled=enabled,
        status=status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_row(row)


def update_binding(
    db: Session,
    binding_id: str,
    *,
    table_name: str | None = None,
    column_name: str | None = None,
    join_template: str | None = None,
    enabled: bool | None = None,
    status: str | None = None,
    notes: str | None = None,
) -> BindingRow | None:
    import uuid as _uuid

    try:
        uid = _uuid.UUID(str(binding_id))
    except Exception:
        return None
    row = db.get(SemanticFieldBinding, uid)
    if not row:
        return None
    if table_name is not None:
        row.table_name = table_name
    if column_name is not None:
        row.column_name = column_name
    if join_template is not None:
        row.join_template = join_template
    if enabled is not None:
        row.enabled = enabled
    if status is not None:
        row.status = status
    if notes is not None:
        row.notes = notes
    row.origin = "manual"
    db.commit()
    db.refresh(row)
    return _to_row(row)


def bindings_as_dicts(rows: list[BindingRow]) -> list[dict[str, Any]]:
    return [
        {
            "id": r.id,
            "concept": r.concept,
            "property_key": r.property_key,
            "source": r.source,
            "table_name": r.table_name,
            "column_name": r.column_name,
            "join_template": r.join_template,
            "notes": r.notes,
            "confidence": r.confidence,
            "origin": r.origin,
            "enabled": r.enabled,
            "status": r.status,
        }
        for r in rows
    ]


def sql_schema_for_editor(db: Session | None = None) -> dict[str, Any]:
    """供前端概念编辑栏选择表/列（白名单 ∩ 实际库列）。"""
    reg = get_sql_binding_registry()
    cols = _introspect_columns(db) if db is not None else {
        t: set(c) for t, c in reg.table_columns.items()
    }
    tables = {
        t: sorted(cols.get(t) or set(reg.table_columns.get(t, ())))
        for t in sorted(executable_sql_tables())
    }
    return {
        "tables": tables,
        "join_templates": sorted(reg.join_template_columns.keys()),
    }
