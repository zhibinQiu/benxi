"""本析平台事务库 → 语义层 SQL 绑定（注入 SqlBindingRegistry）。"""

from __future__ import annotations

from app.semantic.ontology.sql_registry import (
    SqlBindingRegistry,
    set_sql_binding_registry,
)

PLATFORM_SQL_REGISTRY = SqlBindingRegistry(
    table_columns={
        "users": frozenset(
            {"id", "email", "phone", "display_name", "username", "status"}
        ),
        "departments": frozenset({"id", "name", "parent_id"}),
        "documents": frozenset({"id", "title", "status", "owner_id"}),
        "user_departments": frozenset({"id", "user_id", "dept_id", "is_primary"}),
    },
    name_columns={
        "users": ("display_name", "username"),
        "departments": ("name",),
        "documents": ("title",),
    },
    sql_bindings={
        ("person", "email"): ("users", "email", "平台用户邮箱（事务库）"),
        ("person", "phone"): ("users", "phone", "平台用户手机（事务库）"),
        ("org", "full_name"): ("departments", "name", "部门名称（事务库）"),
        ("doc", "document_id"): ("documents", "id", "平台文档 ID"),
    },
    sql_join_bindings={
        ("person", "department"): (
            "person_org",
            "人员所属部门（users ⋈ user_departments ⋈ departments）",
        ),
    },
    join_template_columns={
        "person_org": ("display_name", "username", "department_name"),
    },
    doc_bindings={
        ("doc", "document_id"): "文档库主键，走 knowledge_retrieve / 文档服务",
    },
    table_platform_id_prop={
        "users": "platform_user_id",
        "departments": "platform_department_id",
    },
)


def register_platform_sql_bindings() -> None:
    """Idempotent: install platform SQL whitelist into semantic."""
    set_sql_binding_registry(PLATFORM_SQL_REGISTRY)
