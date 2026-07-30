"""通用 SqlPlanner 单测。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.semantic.models import FieldBinding, SqlPlanStep
from app.semantic.ontology.sql_planner import SqlPlanner, detect_aggregation
from app.semantic.sql_executor import SqlExecutorError, execute_sql_plan_step


def test_detect_aggregation_generic():
    assert detect_aggregation("一共有多少条记录") == "count"
    assert detect_aggregation("how many users") == "count"
    assert detect_aggregation("金额合计是多少") == "sum"
    assert detect_aggregation("查询邮箱") == "none"


def test_sql_planner_builds_select_and_join():
    planner = SqlPlanner()
    steps = planner.plan(
        [
            FieldBinding(
                concept="person",
                property_key="email",
                source="sql",
                table="users",
                column="email",
            ),
            FieldBinding(
                concept="person",
                property_key="department",
                source="sql",
                join_template="person_org",
            ),
        ],
        "某人的邮箱和部门",
    )
    assert any(s.table == "users" and "email" in s.columns for s in steps)
    assert any(s.join_template == "person_org" for s in steps)
    assert all(s.params.get("agg") == "none" for s in steps)


def test_sql_planner_count_ast():
    steps = SqlPlanner().plan(
        [
            FieldBinding(
                concept="person",
                property_key="phone",
                source="sql",
                table="users",
                column="phone",
            )
        ],
        "有多少个匹配",
    )
    assert len(steps) == 1
    assert steps[0].params.get("agg") == "count"
    assert "COUNT" in steps[0].sql.upper()


def test_sql_executor_count_with_name_filter():
    result = MagicMock()
    result.mappings.return_value.first.return_value = {"cnt": 3}
    db = MagicMock()
    db.execute.return_value = result

    step = SqlPlanStep(
        description="count",
        sql="SELECT COUNT(*) AS cnt FROM users",
        params={"agg": "count", "name_tokens": ["张三"], "ids": []},
        table="users",
        columns=["cnt"],
    )
    text_out = execute_sql_plan_step(db, step)
    assert "COUNT" in text_out
    assert "3" in text_out
    sql_arg = str(db.execute.call_args[0][0])
    assert "COUNT" in sql_arg.upper()


def test_sql_executor_count_rejects_unfiltered():
    db = MagicMock()
    step = SqlPlanStep(
        description="count",
        sql="",
        params={"agg": "count", "name_tokens": [], "ids": []},
        table="users",
        columns=["cnt"],
    )
    with pytest.raises(SqlExecutorError, match="全表"):
        execute_sql_plan_step(db, step)


def test_path_planner_uses_sql_planner_question():
    from app.semantic.ontology.path_planner import PathPlanner

    plan = PathPlanner().plan(
        "有多少",
        concepts=[],
        bindings=[
            FieldBinding(
                concept="person",
                property_key="email",
                source="sql",
                table="users",
                column="email",
            )
        ],
    )
    assert plan.sql_steps
    assert plan.sql_steps[0].params.get("agg") == "count"
