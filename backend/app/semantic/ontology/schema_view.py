"""精简 TBox 视图 — 经宿主注入的本体只读端口，不直连 GraphDB。"""

from __future__ import annotations

from typing import Any, Protocol


class OntologySchemaPort(Protocol):
    """本体 Schema 只读端口（由平台 OntologyService 等实现）。"""

    async def compact_schema(
        self,
        question: str = "",
        *,
        type_codes: list[str] | None = None,
        limit_types: int = 12,
    ) -> str: ...

    async def list_entity_types(self, *, include_counts: bool = False) -> list[Any]: ...

    async def list_relation_types(self, *, include_counts: bool = False) -> list[Any]: ...

    async def get_transitive_relation_types(self) -> list[str]: ...

    async def get_inverse_relation_types(self) -> dict[str, str]: ...

    async def get_entity_type_label(self, type_code: str) -> str: ...

    async def get_relation_type_label(self, type_code: str) -> str: ...


class SchemaView:
    """本体 Schema 只读视图；须注入 ``OntologySchemaPort``。"""

    def __init__(self, ontology: OntologySchemaPort) -> None:
        self._ontology = ontology

    async def compact(
        self,
        question: str = "",
        *,
        type_codes: list[str] | None = None,
        limit_types: int = 12,
    ) -> str:
        return await self._ontology.compact_schema(
            question, type_codes=type_codes, limit_types=limit_types
        )

    async def list_entity_types(self, *, include_counts: bool = False) -> list[Any]:
        return await self._ontology.list_entity_types(include_counts=include_counts)

    async def list_relation_types(self, *, include_counts: bool = False) -> list[Any]:
        return await self._ontology.list_relation_types(include_counts=include_counts)

    async def transitive_relation_codes(self) -> list[str]:
        return await self._ontology.get_transitive_relation_types()

    async def inverse_relation_map(self) -> dict[str, str]:
        return await self._ontology.get_inverse_relation_types()

    async def entity_type_label(self, type_code: str) -> str:
        return await self._ontology.get_entity_type_label(type_code)

    async def relation_type_label(self, type_code: str) -> str:
        return await self._ontology.get_relation_type_label(type_code)
