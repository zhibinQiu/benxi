"""受控只读 SQL 与 FieldMapper 白名单。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.semantic.models import MatchedEntity, ResolvedConcept, SqlPlanStep
from app.semantic.ontology.field_mapper import (
    FieldMapper,
    allowed_columns_for_table,
    executable_sql_tables,
)
from app.semantic.sql_executor import (
    SqlExecutorError,
    enrich_sql_step_params,
    execute_sql_plan_step,
)


def test_field_mapper_binds_real_tables_only():
    mapper = FieldMapper()
    concepts = [
        ResolvedConcept(type_code="person", property_keys=["email", "phone"]),
        ResolvedConcept(type_code="org", property_keys=["full_name"]),
        ResolvedConcept(type_code="metric", property_keys=["unit"]),
    ]
    bindings = mapper.map_concepts(concepts)
    sql = [b for b in bindings if b.source == "sql"]
    tables = {b.table for b in sql}
    assert tables <= executable_sql_tables()
    assert "users" in tables
    assert "departments" in tables
    assert "persons" not in tables
    assert "metrics" not in tables
    email = next(b for b in sql if b.column == "email")
    assert email.table == "users"


def test_sql_executor_rejects_unknown_table():
    db = MagicMock()
    step = SqlPlanStep(
        description="x",
        sql="SELECT id FROM evil",
        params={"ids": [str(uuid.uuid4())]},
        table="evil",
        columns=["id"],
    )
    with pytest.raises(SqlExecutorError, match="白名单"):
        execute_sql_plan_step(db, step)


def test_sql_executor_rejects_unfiltered_scan():
    db = MagicMock()
    step = SqlPlanStep(
        description="x",
        sql="SELECT id FROM users",
        params={},
        table="users",
        columns=["id", "email"],
    )
    with pytest.raises(SqlExecutorError, match="全表"):
        execute_sql_plan_step(db, step)


def test_sql_executor_runs_id_filter():
    uid = uuid.uuid4()
    row = {"id": uid, "email": "a@b.com"}
    result = MagicMock()
    result.mappings.return_value.all.return_value = [row]
    db = MagicMock()
    db.execute.return_value = result

    step = SqlPlanStep(
        description="x",
        sql="SELECT id, email FROM users",
        params={"ids": [str(uid)]},
        table="users",
        columns=["id", "email"],
    )
    text_out = execute_sql_plan_step(db, step)
    assert "a@b.com" in text_out
    assert "users" in text_out
    sql_arg = db.execute.call_args[0][0]
    assert "ANY" in str(sql_arg)


def test_enrich_params_from_matched_platform_ids():
    uid = str(uuid.uuid4())
    step = SqlPlanStep(
        description="x",
        sql="",
        params={},
        table="users",
        columns=["id", "email"],
    )
    enriched = enrich_sql_step_params(
        step,
        matched=[
            MatchedEntity(
                id="e1",
                name="邱智斌",
                type_code="person",
                props={"platform_user_id": uid},
            )
        ],
        question="邱智斌的邮箱",
    )
    assert uid in enriched.params["ids"]
    assert "邱智斌" in enriched.params["name_tokens"]


def test_allowed_columns_users():
    cols = allowed_columns_for_table("users")
    assert "email" in cols
    assert "password_hash" not in cols


def test_execute_plan_appends_sql_context():
    import asyncio

    from app.semantic.kg.reasoning import ReasoningPayload
    from app.semantic.kg.service import KgQueryService
    from app.semantic.models import QueryPlan

    svc = KgQueryService(driver=MagicMock())

    async def _fake_plan(plan, matched):
        return ReasoningPayload(
            context_text="图谱上下文",
            has_material=True,
            matched_entities=list(matched or []),
        )

    svc._get_reasoning = MagicMock(
        return_value=SimpleNamespace(execute_query_plan=_fake_plan)
    )

    uid = uuid.uuid4()
    row = {"id": uid, "email": "x@y.com"}
    result = MagicMock()
    result.mappings.return_value.all.return_value = [row]
    db = MagicMock()
    db.execute.return_value = result

    plan = QueryPlan(
        question="邮箱",
        sql_steps=[
            SqlPlanStep(
                description="users",
                sql="SELECT id, email FROM users",
                params={"ids": [str(uid)]},
                table="users",
                columns=["id", "email"],
            )
        ],
    )

    async def _run():
        return await svc.execute_plan(
            plan,
            "owner",
            matched=[
                MatchedEntity(
                    id="e1",
                    name="张三",
                    type_code="person",
                    props={"platform_user_id": str(uid)},
                )
            ],
            db=db,
        )

    payload = asyncio.run(_run())
    assert "【SQL 证据】" in payload.context_text
    assert "x@y.com" in payload.context_text
    assert any(c.get("source") == "sql" for c in payload.citations)
