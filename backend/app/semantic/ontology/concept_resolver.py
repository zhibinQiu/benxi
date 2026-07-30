"""自然语言 → 本体概念（Class / Property / Relation）解析。"""

from __future__ import annotations

from typing import Any

from app.semantic.defaults import DEFAULT_ENTITY_TYPES, DEFAULT_RELATION_TYPES
from app.semantic.models import ResolvedConcept

from .schema_view import SchemaView

# 常见同义 / 口语 → type_code
_ALIAS_TO_CODE: dict[str, str] = {
    "组织": "org",
    "公司": "org",
    "企业": "org",
    "单位": "org",
    "部门": "org",
    "机构": "org",
    "人员": "person",
    "员工": "person",
    "同事": "person",
    "成员": "person",
    "人": "person",
    "文档": "doc",
    "文件": "doc",
    "法规": "regulation",
    "标准": "regulation",
    "政策": "regulation",
    "项目": "project",
    "指标": "metric",
    "工具": "tool",
    "技能": "skill",
    "智能体": "agent",
    "agent": "agent",
    "记忆": "memory",
}


def _field(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class ConceptResolver:
    """将问题中的业务用语映射到本体类型与相关关系。"""

    def __init__(self, schema: SchemaView | None = None) -> None:
        self._schema = schema

    async def resolve(self, question: str, *, limit: int = 8) -> list[ResolvedConcept]:
        q = (question or "").strip()
        if not q:
            return []
        q_l = q.lower()

        entity_types = await self._load_entity_types()
        relation_types = await self._load_relation_types()

        hits: list[ResolvedConcept] = []
        seen: set[str] = set()

        for et in entity_types:
            code = str(_field(et, "code") or "").strip()
            label = str(_field(et, "label") or "").strip()
            if not code or code in seen:
                continue
            aliases = [label, code] if label else [code]
            for alias, mapped in _ALIAS_TO_CODE.items():
                if mapped == code:
                    aliases.append(alias)
            matched_alias = ""
            for alias in aliases:
                a = (alias or "").strip()
                if len(a) < 1:
                    continue
                if a.lower() in q_l or a in q:
                    matched_alias = a
                    break
            if not matched_alias:
                continue
            prop_schema = _field(et, "property_schema") or {}
            if hasattr(prop_schema, "items"):
                prop_keys = list(prop_schema.keys())
            else:
                prop_keys = []
            rel_codes = [
                str(_field(rt, "code") or "")
                for rt in relation_types
                if code
                in (
                    list(_field(rt, "domain_types") or [])
                    + list(_field(rt, "range_types") or [])
                )
            ]
            rel_codes = [c for c in rel_codes if c]
            conf = 0.9 if matched_alias == label or matched_alias == code else 0.7
            hits.append(
                ResolvedConcept(
                    type_code=code,
                    label=label or code,
                    property_keys=prop_keys,
                    relation_codes=list(dict.fromkeys(rel_codes))[:12],
                    aliases_hit=[matched_alias],
                    confidence=conf,
                    rationale=f"问题命中概念别名「{matched_alias}」→ {code}",
                )
            )
            seen.add(code)
            if len(hits) >= limit:
                break

        hits.sort(key=lambda c: (-c.confidence, c.type_code))
        return hits

    async def _load_entity_types(self) -> list[Any]:
        if self._schema is None:
            return DEFAULT_ENTITY_TYPES
        try:
            types = await self._schema.list_entity_types(include_counts=False)
            if types:
                return types
        except Exception:
            pass
        return DEFAULT_ENTITY_TYPES

    async def _load_relation_types(self) -> list[Any]:
        if self._schema is None:
            return DEFAULT_RELATION_TYPES
        try:
            types = await self._schema.list_relation_types(include_counts=False)
            if types:
                return types
        except Exception:
            pass
        return DEFAULT_RELATION_TYPES
