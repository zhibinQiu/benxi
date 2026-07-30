"""查询路径规划 — 只生成 Neo4j/SQL 计划，不执行。"""

from __future__ import annotations

from typing import Sequence

from app.semantic.models import (
    FieldBinding,
    MatchedEntity,
    Neo4jPlanStep,
    QueryPlan,
    ResolvedConcept,
    SqlPlanStep,
)

from .intents import detect_intent_tags, tools_for_intents


class PathPlanner:
    """根据概念、意图与实体线索生成 QueryPlan。"""

    def plan(
        self,
        question: str,
        *,
        concepts: list[ResolvedConcept],
        bindings: list[FieldBinding],
        matched: Sequence[MatchedEntity] | None = None,
        owner_id: str = "",
        max_depth: int = 3,
        include_inferred: bool = True,
        transitive_codes: list[str] | None = None,
        inverse_map: dict[str, str] | None = None,
    ) -> QueryPlan:
        q = (question or "").strip()
        intent_tags = detect_intent_tags(q)
        preferred, blocked = tools_for_intents(intent_tags)
        matched_list = list(matched or [])

        # 命中概念或实体时优先图谱
        if (concepts or matched_list) and "kg_query" not in preferred:
            preferred = ["kg_query", *preferred]
        if concepts and "ontology_query" not in preferred and not matched_list:
            preferred = [*preferred, "ontology_query"]
        preferred = list(dict.fromkeys(preferred))
        blocked = list(dict.fromkeys(blocked))

        sql_steps = self._build_sql_steps(bindings, q)
        neo4j_steps: list[Neo4jPlanStep] = []
        preferred_rels: list[str] = []
        for c in concepts:
            for rc in c.relation_codes or []:
                if rc and rc not in preferred_rels:
                    preferred_rels.append(rc)

        if matched_list and owner_id:
            neo4j_steps = self.build_abox_plan(
                matched_list,
                owner_id,
                max_depth=max_depth,
                include_inferred=include_inferred,
                transitive_codes=transitive_codes or [],
                inverse_map=inverse_map or {},
                preferred_relation_codes=preferred_rels,
            ).neo4j_steps
        elif concepts:
            neo4j_steps = self._build_schema_path_templates(concepts)

        why = self._build_why(q, intent_tags, concepts, bindings, neo4j_steps, sql_steps)

        return QueryPlan(
            question=q,
            intent_tags=intent_tags,
            concepts=list(concepts),
            field_bindings=list(bindings),
            neo4j_steps=neo4j_steps,
            sql_steps=sql_steps,
            preferred_tools=preferred,
            blocked_tools=blocked,
            why=why,
            matched_entity_ids=[e.id for e in matched_list],
        )

    def build_abox_plan(
        self,
        matched: Sequence[MatchedEntity],
        owner_id: str,
        *,
        max_depth: int = 3,
        include_inferred: bool = True,
        transitive_codes: list[str] | None = None,
        inverse_map: dict[str, str] | None = None,
        preferred_relation_codes: list[str] | None = None,
        path_limit: int = 80,
    ) -> QueryPlan:
        """从已匹配实体构建可执行 Neo4j 多跳计划（1 跳邻域 + 通用变长路径）。"""
        entity_ids = [e.id for e in matched if e.id]
        steps: list[Neo4jPlanStep] = [
            Neo4jPlanStep(
                description="直接关联实体",
                cypher="""
                    MATCH (a:Entity)-[r:RELATES]-(b:Entity)
                    WHERE a.id IN $ids AND b.owner_id = $owner
                    RETURN a.id AS source_id, a.name AS source_name,
                           a.type_code AS source_type,
                           r.id AS rel_id, r.type_code AS rel_type,
                           r.description AS rel_desc, r.inferred AS rel_inferred,
                           b.id AS target_id, b.name AS target_name,
                           b.type_code AS target_type,
                           1 AS hops
                """,
                params={"ids": entity_ids, "owner": owner_id},
            )
        ]
        if include_inferred:
            depth = max(1, min(int(max_depth), 5))
            limit = max(10, min(int(path_limit), 200))
            rel_codes = [
                c.replace("'", "")
                for c in (preferred_relation_codes or [])
                if c and c.strip()
            ]
            # 通用多跳：任意业务 RELATES；有本体关系线索时优先约束边类型
            if rel_codes:
                codes_lit = ", ".join(f"'{c}'" for c in rel_codes)
                filter_clause = f"AND ALL(r IN relationships(path) WHERE r.type_code IN [{codes_lit}])"
                desc = f"通用多跳路径(≤{depth}，约束关系 {','.join(rel_codes[:6])})"
            else:
                filter_clause = ""
                desc = f"通用多跳路径(≤{depth})"
            steps.append(
                Neo4jPlanStep(
                    description=desc,
                    cypher=f"""
                        MATCH path = (a:Entity)-[:RELATES*1..{depth}]-(b:Entity)
                        WHERE a.id IN $ids
                          AND b.owner_id = $owner
                          AND a <> b
                          {filter_clause}
                        WITH path, nodes(path) AS ns, relationships(path) AS rs,
                             length(path) AS hops
                        ORDER BY hops ASC
                        LIMIT $limit
                        RETURN
                          [n IN ns | {{
                            id: n.id, name: n.name, type_code: n.type_code
                          }}] AS path_nodes,
                          [i IN range(0, size(rs)-1) | {{
                            type_code: rs[i].type_code,
                            forward: startNode(rs[i]) = ns[i]
                          }}] AS path_edges,
                          [r IN rs | r.type_code] AS path_rels,
                          hops,
                          true AS is_inferred,
                          ns[0].id AS source_id,
                          ns[0].name AS source_name,
                          ns[0].type_code AS source_type,
                          ns[-1].id AS target_id,
                          ns[-1].name AS target_name,
                          ns[-1].type_code AS target_type,
                          CASE WHEN size(rs) > 0 THEN rs[0].type_code ELSE '' END AS rel_type
                    """,
                    params={"ids": entity_ids, "owner": owner_id, "limit": limit},
                )
            )
            # 传递闭包：同类型边补充（与通用多跳结果去重）
            for rel_code in transitive_codes or []:
                safe = rel_code.replace("'", "")
                if safe in rel_codes:
                    continue
                steps.append(
                    Neo4jPlanStep(
                        description=f"传递推理: {safe}",
                        cypher=f"""
                            MATCH path = (a:Entity)-[:RELATES*1..{depth}
                                {{type_code: '{safe}'}}]-(b:Entity)
                            WHERE a.id IN $ids AND b.owner_id = $owner AND a <> b
                            WITH path, nodes(path) AS ns, relationships(path) AS rs,
                                 length(path) AS hops
                            ORDER BY hops ASC
                            LIMIT $limit
                            RETURN
                              [n IN ns | {{
                                id: n.id, name: n.name, type_code: n.type_code
                              }}] AS path_nodes,
                              [i IN range(0, size(rs)-1) | {{
                                type_code: rs[i].type_code,
                                forward: startNode(rs[i]) = ns[i]
                              }}] AS path_edges,
                              [r IN rs | r.type_code] AS path_rels,
                              hops,
                              true AS is_inferred,
                              '{safe}' AS rel_type,
                              ns[0].id AS source_id,
                              ns[0].name AS source_name,
                              ns[0].type_code AS source_type,
                              ns[-1].id AS target_id,
                              ns[-1].name AS target_name,
                              ns[-1].type_code AS target_type
                        """,
                        params={
                            "ids": entity_ids,
                            "owner": owner_id,
                            "limit": limit,
                        },
                    )
                )
            for rel_code, inverse_code in (inverse_map or {}).items():
                safe_inv = inverse_code.replace("'", "")
                steps.append(
                    Neo4jPlanStep(
                        description=f"逆关系推理: {rel_code} → {safe_inv}",
                        cypher=f"""
                            MATCH (a:Entity)-[r:RELATES
                                {{type_code: '{safe_inv}'}}]->(b:Entity)
                            WHERE b.id IN $ids
                            RETURN a.id AS source_id, a.name AS source_name,
                                   a.type_code AS source_type,
                                   'inverse_of_{safe_inv}' AS rel_type,
                                   b.id AS target_id, b.name AS target_name,
                                   b.type_code AS target_type,
                                   1 AS hops,
                                   true AS is_inferred
                        """,
                        params={"ids": entity_ids},
                    )
                )
        return QueryPlan(
            neo4j_steps=steps,
            matched_entity_ids=entity_ids,
            why="基于命中实体生成 Neo4j 邻域/通用多跳/互逆查询路径",
        )

    def _build_schema_path_templates(
        self, concepts: list[ResolvedConcept]
    ) -> list[Neo4jPlanStep]:
        """无实体 id 时：按概念关系给出路径模板（供说明，执行前需补实体）。"""
        steps: list[Neo4jPlanStep] = []
        for c in concepts[:4]:
            for rel in (c.relation_codes or [])[:3]:
                safe = rel.replace("'", "")
                steps.append(
                    Neo4jPlanStep(
                        description=f"概念路径 {c.type_code}-[{safe}]->*",
                        cypher=f"""
                            MATCH (a:Entity {{type_code: $type_code}})-[r:RELATES
                                {{type_code: '{safe}'}}]-(b:Entity)
                            WHERE a.owner_id = $owner
                            RETURN a.id AS source_id, a.name AS source_name,
                                   a.type_code AS source_type,
                                   r.type_code AS rel_type,
                                   b.id AS target_id, b.name AS target_name,
                                   b.type_code AS target_type
                            LIMIT 50
                        """,
                        params={"type_code": c.type_code, "owner": ""},
                    )
                )
        return steps

    def _build_sql_steps(
        self, bindings: list[FieldBinding], question: str
    ) -> list[SqlPlanStep]:
        from app.semantic.ontology.sql_planner import SqlPlanner

        return SqlPlanner().plan(bindings, question)

    def _build_why(
        self,
        question: str,
        intent_tags: list[str],
        concepts: list[ResolvedConcept],
        bindings: list[FieldBinding],
        neo4j_steps: list[Neo4jPlanStep],
        sql_steps: list[SqlPlanStep],
    ) -> str:
        bits: list[str] = []
        if question:
            bits.append(f"用户问的是「{question[:80]}」")
        if intent_tags:
            bits.append(f"识别意图 {','.join(intent_tags)}")
        if concepts:
            bits.append(
                "映射概念 "
                + ", ".join(f"{c.label or c.type_code}" for c in concepts[:5])
            )
        sources = sorted({b.source for b in bindings})
        if sources:
            bits.append(f"应查数据源: {', '.join(sources)}")
        if neo4j_steps:
            bits.append(f"Neo4j 路径 {len(neo4j_steps)} 步")
        if sql_steps:
            bits.append(f"SQL 路径 {len(sql_steps)} 步（受控只读）")
        if not bits:
            return "未识别到明确业务概念，建议补充实体名或类型后再查"
        return "；".join(bits) + "。"
