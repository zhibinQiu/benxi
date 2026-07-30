"""通用受控 SQL 规划器 — 从字段绑定组装 AST 风格计划，不针对具体业务场景。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from app.semantic.models import FieldBinding, SqlPlanStep

from .field_mapper import (
    executable_sql_tables,
    join_template_columns,
    registered_join_templates,
)

# 通用聚合意图（语言中立关键词，非场景特化）
_AGG_COUNT_RE = re.compile(
    r"(?:多少|几个|几名|几位|计数|数量|总数|count\b|how\s+many)",
    re.I,
)
_AGG_SUM_RE = re.compile(
    r"(?:合计|总和|累计|求和|sum\b|total\b)",
    re.I,
)


AggKind = Literal["none", "count", "sum"]


@dataclass(slots=True)
class SqlSelectAst:
    """受控 SELECT 的轻量 AST（仅规划，不直接拼接未校验标识符）。"""

    table: str = ""
    columns: list[str] = field(default_factory=list)
    join_template: str = ""
    agg: AggKind = "none"
    agg_column: str = ""
    filter_mode: Literal["anchor_or_name", "none"] = "anchor_or_name"
    description: str = ""


def detect_aggregation(question: str) -> AggKind:
    q = (question or "").strip()
    if not q:
        return "none"
    if _AGG_SUM_RE.search(q):
        return "sum"
    if _AGG_COUNT_RE.search(q):
        return "count"
    return "none"


def _pick_sum_column(columns: list[str]) -> str:
    """从已绑定列中选可求和列；无数值暗示则回退首列（执行器再校验）。"""
    numeric_hints = ("amount", "qty", "quantity", "count", "total", "value", "score", "num")
    for c in columns:
        low = c.lower()
        if any(h in low for h in numeric_hints):
            return c
    return columns[0] if columns else "id"


class SqlPlanner:
    """按绑定图生成 SqlPlanStep：锚点 IN / 名称过滤 / COUNT|SUM / 注册制 join。"""

    def plan(
        self,
        bindings: list[FieldBinding],
        question: str = "",
    ) -> list[SqlPlanStep]:
        agg = detect_aggregation(question)
        asts = self.build_asts(bindings, agg=agg)
        return [self.ast_to_step(a) for a in asts]

    def build_asts(
        self,
        bindings: list[FieldBinding],
        *,
        agg: AggKind = "none",
    ) -> list[SqlSelectAst]:
        steps: list[SqlSelectAst] = []
        seen_templates: set[str] = set()
        by_table: dict[str, list[FieldBinding]] = {}

        for b in bindings:
            if b.source != "sql":
                continue
            tmpl = (b.join_template or "").strip()
            if tmpl:
                if tmpl not in registered_join_templates() or tmpl in seen_templates:
                    continue
                seen_templates.add(tmpl)
                cols = list(join_template_columns(tmpl))
                steps.append(
                    SqlSelectAst(
                        join_template=tmpl,
                        columns=cols,
                        agg="none",  # 联查模板先出明细；聚合可后续扩展
                        description=f"受控联查 {tmpl}（{b.concept}.{b.property_key}）",
                    )
                )
                continue
            table = (b.table or "").strip()
            if not table or table not in executable_sql_tables():
                continue
            by_table.setdefault(table, []).append(b)

        for table, cols_bind in by_table.items():
            columns = list(dict.fromkeys(c.column for c in cols_bind if c.column))
            if "id" not in columns:
                columns.insert(0, "id")
            use_agg = agg
            agg_col = ""
            if use_agg == "sum":
                agg_col = _pick_sum_column([c for c in columns if c != "id"] or columns)
            desc = f"受控查询 {table}"
            if use_agg == "count":
                desc = f"受控计数 COUNT({table})"
            elif use_agg == "sum" and agg_col:
                desc = f"受控求和 SUM({table}.{agg_col})"
            else:
                desc = f"受控只读查询表 {table} 字段 {', '.join(columns)}"
            steps.append(
                SqlSelectAst(
                    table=table,
                    columns=columns,
                    agg=use_agg if use_agg != "none" else "none",
                    agg_column=agg_col,
                    description=desc,
                )
            )
        return steps

    def ast_to_step(self, ast: SqlSelectAst) -> SqlPlanStep:
        params: dict = {
            "name_tokens": [],
            "ids": [],
            "agg": ast.agg,
            "agg_column": ast.agg_column,
        }
        if ast.join_template:
            return SqlPlanStep(
                description=ast.description,
                sql="",
                params=params,
                join_template=ast.join_template,
                columns=list(ast.columns),
            )
        # sql 字段仅作说明；执行器按 table/columns/params 重建
        if ast.agg == "count":
            sql = f"SELECT COUNT(*) AS cnt FROM {ast.table}"
            columns = ["cnt"]
        elif ast.agg == "sum" and ast.agg_column:
            sql = f"SELECT SUM({ast.agg_column}) AS total FROM {ast.table}"
            columns = ["total"]
        else:
            col_sql = ", ".join(ast.columns)
            sql = f"SELECT {col_sql} FROM {ast.table}"
            columns = list(ast.columns)
        return SqlPlanStep(
            description=ast.description,
            sql=sql,
            params=params,
            table=ast.table,
            columns=columns,
        )
