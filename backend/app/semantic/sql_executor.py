"""受控只读 SQL：仅执行本体 FieldMapper 白名单内的 SELECT / 注册联查模板。"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.semantic.models import MatchedEntity, SqlPlanStep
from app.semantic.ontology.sql_registry import (
    allowed_columns_for_table,
    executable_sql_tables,
    get_sql_binding_registry,
    join_template_columns,
    name_columns_for_table,
    registered_join_templates,
)

logger = logging.getLogger(__name__)

_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]*$", re.I)
_MAX_ROWS = 20
_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9][\w.-]{1,}", re.UNICODE)


class SqlExecutorError(ValueError):
    """受控 SQL 校验失败。"""


def question_name_tokens(question: str) -> list[str]:
    return [m.group(0) for m in _TOKEN_RE.finditer((question or "").strip())]


def enrich_sql_step_params(
    step: SqlPlanStep,
    *,
    matched: list[MatchedEntity] | None = None,
    question: str = "",
) -> SqlPlanStep:
    """根据命中实体 / 问题 token 填充 ids 与 name_tokens。"""
    table = (step.table or "").strip()
    template = (step.join_template or "").strip()
    ids: list[str] = []
    names: list[str] = []
    id_prop = get_sql_binding_registry().table_platform_id_prop.get(table)
    if template == "person_org":
        id_prop = "platform_user_id"
    for ent in matched or []:
        if id_prop and ent.props.get(id_prop):
            ids.append(str(ent.props[id_prop]))
        if (ent.name or "").strip():
            names.append(ent.name.strip())
    tokens = list(dict.fromkeys(names + question_name_tokens(question)))
    params = dict(step.params or {})
    params["ids"] = list(dict.fromkeys(ids))
    params["name_tokens"] = tokens
    return SqlPlanStep(
        description=step.description,
        sql=step.sql,
        params=params,
        table=step.table,
        columns=list(step.columns or []),
        join_template=step.join_template,
    )


def _quote_ident(name: str) -> str:
    if not _IDENT_RE.match(name):
        raise SqlExecutorError(f"非法标识符: {name}")
    return name


def _build_name_or_id_filter(
    *,
    raw_ids: list[str],
    name_tokens: list[str],
    name_cols: tuple[str, ...],
    id_expr: str = "id",
) -> tuple[list[str], dict[str, Any]]:
    bind: dict[str, Any] = {"lim": _MAX_ROWS}
    where_parts: list[str] = []
    if raw_ids:
        uuids: list[uuid.UUID] = []
        for s in raw_ids:
            try:
                uuids.append(uuid.UUID(s))
            except ValueError as exc:
                raise SqlExecutorError(f"非法 id: {s}") from exc
        where_parts.append(f"{id_expr} = ANY(:ids)")
        bind["ids"] = uuids
    elif name_tokens:
        if not name_cols:
            raise SqlExecutorError("无名称过滤列")
        or_bits: list[str] = []
        for i, tok in enumerate(name_tokens[:8]):
            key = f"tok{i}"
            bind[key] = tok
            for col in name_cols:
                or_bits.append(f"{_quote_ident(col)} ILIKE '%' || :{key} || '%'")
        where_parts.append("(" + " OR ".join(or_bits) + ")")
    else:
        raise SqlExecutorError("拒绝无过滤条件的全表查询")
    return where_parts, bind


def _execute_join_template(db: Session, step: SqlPlanStep) -> str:
    template = (step.join_template or "").strip()
    if template not in registered_join_templates():
        raise SqlExecutorError(f"未知联查模板: {template}")
    params = dict(step.params or {})
    raw_ids = [str(x).strip() for x in (params.get("ids") or []) if str(x).strip()]
    name_tokens = [
        str(x).strip()
        for x in (params.get("name_tokens") or [])
        if str(x).strip() and len(str(x).strip()) >= 2
    ]
    columns = list(join_template_columns(template))

    if template != "person_org":
        raise SqlExecutorError(f"联查模板未实现: {template}")

    bind: dict[str, Any] = {"lim": _MAX_ROWS}
    if raw_ids:
        uuids: list[uuid.UUID] = []
        for s in raw_ids:
            try:
                uuids.append(uuid.UUID(s))
            except ValueError as exc:
                raise SqlExecutorError(f"非法 id: {s}") from exc
        bind["ids"] = uuids
        where_sql = "u.id = ANY(:ids)"
    elif name_tokens:
        or_bits: list[str] = []
        for i, tok in enumerate(name_tokens[:8]):
            key = f"tok{i}"
            bind[key] = tok
            or_bits.append(f"u.display_name ILIKE '%' || :{key} || '%'")
            or_bits.append(f"u.username ILIKE '%' || :{key} || '%'")
        where_sql = "(" + " OR ".join(or_bits) + ")"
    else:
        raise SqlExecutorError("拒绝无过滤条件的全表查询")

    sql = f"""
        SELECT u.display_name AS display_name,
               u.username AS username,
               d.name AS department_name
        FROM users u
        JOIN user_departments ud ON ud.user_id = u.id
        JOIN departments d ON d.id = ud.dept_id
        WHERE {where_sql}
        LIMIT :lim
    """
    rows = db.execute(text(sql), bind).mappings().all()
    label = f"SQL {template}"
    if not rows:
        return f"[{label}] 无匹配行"
    lines = [f"[{label}] 共 {len(rows)} 行"]
    for row in rows[:_MAX_ROWS]:
        parts = [f"{k}={row[k]}" for k in columns if k in row and row[k] is not None]
        lines.append("- " + "; ".join(parts))
    return "\n".join(lines)


def _validate_step(step: SqlPlanStep) -> tuple[str, list[str]]:
    table = (step.table or "").strip()
    if table not in executable_sql_tables():
        raise SqlExecutorError(f"表不在白名单: {table}")
    allowed = allowed_columns_for_table(table)
    columns = [c for c in (step.columns or []) if c]
    if not columns:
        raise SqlExecutorError("未指定列")
    for col in columns:
        if col not in allowed:
            raise SqlExecutorError(f"列不在白名单: {table}.{col}")
        _quote_ident(col)
    _quote_ident(table)
    return table, columns


def execute_sql_plan_step(db: Session, step: SqlPlanStep) -> str:
    """执行单步受控 SELECT / 聚合或注册联查；无过滤条件则拒绝。"""
    if (step.join_template or "").strip():
        return _execute_join_template(db, step)

    params = dict(step.params or {})
    agg = str(params.get("agg") or "none").lower()
    table = (step.table or "").strip()
    if table not in executable_sql_tables():
        raise SqlExecutorError(f"表不在白名单: {table}")
    _quote_ident(table)

    raw_ids = [str(x).strip() for x in (params.get("ids") or []) if str(x).strip()]
    name_tokens = [
        str(x).strip()
        for x in (params.get("name_tokens") or [])
        if str(x).strip() and len(str(x).strip()) >= 2
    ]
    where_parts, bind = _build_name_or_id_filter(
        raw_ids=raw_ids,
        name_tokens=name_tokens,
        name_cols=name_columns_for_table(table),
    )
    where_sql = " AND ".join(where_parts)

    if agg == "count":
        sql = (
            f"SELECT COUNT(*) AS cnt FROM {_quote_ident(table)} "
            f"WHERE {where_sql}"
        )
        row = db.execute(text(sql), bind).mappings().first()
        cnt = int(row["cnt"]) if row and row.get("cnt") is not None else 0
        return f"[SQL {table} COUNT] {cnt}"

    if agg == "sum":
        agg_col = str(params.get("agg_column") or "").strip()
        allowed = allowed_columns_for_table(table)
        if not agg_col or agg_col not in allowed:
            raise SqlExecutorError(f"聚合列不在白名单: {table}.{agg_col}")
        _quote_ident(agg_col)
        sql = (
            f"SELECT SUM({_quote_ident(agg_col)}) AS total FROM {_quote_ident(table)} "
            f"WHERE {where_sql}"
        )
        row = db.execute(text(sql), bind).mappings().first()
        total = row["total"] if row else None
        return f"[SQL {table} SUM({agg_col})] {total}"

    table, columns = _validate_step(step)
    col_sql = ", ".join(_quote_ident(c) for c in columns)
    sql = (
        f"SELECT {col_sql} FROM {_quote_ident(table)} "
        f"WHERE {where_sql} LIMIT :lim"
    )
    rows = db.execute(text(sql), bind).mappings().all()
    if not rows:
        return f"[SQL {table}] 无匹配行"
    lines = [f"[SQL {table}] 共 {len(rows)} 行"]
    for row in rows[:_MAX_ROWS]:
        parts = [f"{k}={row[k]}" for k in columns if k in row and row[k] is not None]
        lines.append("- " + "; ".join(parts))
    return "\n".join(lines)


def execute_sql_steps(
    db: Session,
    steps: list[SqlPlanStep],
    *,
    matched: list[MatchedEntity] | None = None,
    question: str = "",
) -> str:
    """批量执行受控 SQL，返回合并摘要；单步失败记入摘要不中断其余步骤。"""
    if not steps:
        return ""
    chunks: list[str] = []
    for step in steps:
        enriched = enrich_sql_step_params(step, matched=matched, question=question)
        label = enriched.join_template or enriched.table or "sql"
        try:
            chunks.append(execute_sql_plan_step(db, enriched))
        except SqlExecutorError as exc:
            logger.info("受控 SQL 跳过 %s: %s", label, exc)
            chunks.append(f"[SQL {label}] 跳过: {exc}")
        except Exception as exc:
            logger.warning("受控 SQL 失败 %s: %s", label, exc)
            chunks.append(f"[SQL {label}] 执行失败")
    return "\n".join(chunks)
