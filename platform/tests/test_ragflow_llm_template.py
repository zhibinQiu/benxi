"""RAGFlow 共享模型配置同步。"""

from __future__ import annotations

from unittest.mock import patch

from app.integrations.ragflow_llm_template import (
    ensure_shared_llm_config,
    resolve_template_tenant_id,
    sync_tenant_llm_from_template,
)


def test_resolve_template_tenant_id_prefers_configured_email():
    with patch(
        "app.integrations.ragflow_llm_template._mysql_query",
        return_value=["tpl-tenant-1"],
    ):
        tid = resolve_template_tenant_id()
    assert tid == "tpl-tenant-1"


def test_sync_skips_when_target_is_template():
    with patch(
        "app.integrations.ragflow_llm_template.resolve_template_tenant_id",
        return_value="same-id",
    ):
        assert sync_tenant_llm_from_template("same-id") is False


def test_sync_copies_llm_rows():
    calls: list[str] = []

    def fake_exec(sql: str) -> bool:
        calls.append(sql)
        return True

    with patch(
        "app.integrations.ragflow_llm_template.resolve_template_tenant_id",
        return_value="admin-id",
    ), patch(
        "app.integrations.ragflow_llm_template._mysql_exec",
        side_effect=fake_exec,
    ):
        ok = sync_tenant_llm_from_template("user-id")

    assert ok is True
    assert len(calls) == 2
    assert "UPDATE tenant" in calls[0]
    assert "INSERT INTO tenant_llm" in calls[1]
    assert "admin-id" in calls[1]
    assert "user-id" in calls[1]


def test_ensure_shared_llm_config_noop_without_user_id():
    assert ensure_shared_llm_config(None) is False
