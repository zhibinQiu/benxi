"""Injectable SQL / document field-binding registry for the semantic layer.

Platform hosts call ``set_sql_binding_registry`` at startup with table whitelists;
semantic cores read via ``get_sql_binding_registry`` and stay free of
hard-coded platform schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SqlBindingRegistry:
    """Whitelist + concept→SQL/document maps used by FieldMapper / SqlExecutor."""

    table_columns: dict[str, frozenset[str]] = field(default_factory=dict)
    name_columns: dict[str, tuple[str, ...]] = field(default_factory=dict)
    sql_bindings: dict[tuple[str, str], tuple[str, str, str]] = field(
        default_factory=dict
    )
    sql_join_bindings: dict[tuple[str, str], tuple[str, str]] = field(
        default_factory=dict
    )
    join_template_columns: dict[str, tuple[str, ...]] = field(default_factory=dict)
    doc_bindings: dict[tuple[str, str], str] = field(default_factory=dict)
    table_platform_id_prop: dict[str, str] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> "SqlBindingRegistry":
        return cls()


_registry: SqlBindingRegistry = SqlBindingRegistry.empty()


def get_sql_binding_registry() -> SqlBindingRegistry:
    return _registry


def set_sql_binding_registry(registry: SqlBindingRegistry) -> None:
    global _registry
    _registry = registry


def executable_sql_tables() -> frozenset[str]:
    return frozenset(get_sql_binding_registry().table_columns)


def allowed_columns_for_table(table: str) -> frozenset[str]:
    return get_sql_binding_registry().table_columns.get(table, frozenset())


def name_columns_for_table(table: str) -> tuple[str, ...]:
    return get_sql_binding_registry().name_columns.get(table, ())


def join_template_columns(template_id: str) -> tuple[str, ...]:
    return get_sql_binding_registry().join_template_columns.get(template_id, ())


def registered_join_templates() -> frozenset[str]:
    return frozenset(get_sql_binding_registry().join_template_columns)
