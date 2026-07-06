"""RAGFlow 共享模型配置同步。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.integrations.ragflow_llm_template import (
    ensure_shared_llm_config,
    resolve_template_tenant_id,
    sync_all_tenant_llm_configs,
    sync_tenant_llm_from_template,
)


def test_resolve_template_tenant_id_prefers_configured_email():
    with patch(
        "app.integrations.ragflow_llm_template._tenant_llm_row_count",
        return_value=3,
    ), patch(
        "app.integrations.ragflow_llm_template._template_tenant_by_email",
        return_value="tpl-tenant-1",
    ), patch(
        "app.integrations.ragflow_llm_template.get_settings",
    ) as gs:
        gs.return_value.ragflow_llm_template_tenant_id = ""
        gs.return_value.ragflow_llm_template_email = "master@platform.local"
        gs.return_value.ragflow_shared_email = ""
        tid = resolve_template_tenant_id()
    assert tid == "tpl-tenant-1"


def test_resolve_template_uses_richest_when_bootstrap_has_no_models():
    db = MagicMock()
    with patch(
        "app.integrations.ragflow_llm_template._template_tenant_from_platform_bootstrap",
        return_value="bootstrap-id",
    ), patch(
        "app.integrations.ragflow_llm_template._tenant_llm_row_count",
        side_effect=lambda tid: 0 if tid == "bootstrap-id" else 5,
    ), patch(
        "app.integrations.ragflow_llm_template._richest_llm_template_tenant_id",
        return_value="richest-id",
    ), patch(
        "app.integrations.ragflow_llm_template.get_settings",
    ) as gs:
        gs.return_value.ragflow_llm_template_tenant_id = ""
        gs.return_value.ragflow_llm_template_email = ""
        gs.return_value.ragflow_shared_email = ""
        tid = resolve_template_tenant_id(db)
    assert tid == "richest-id"


def test_sync_skips_when_target_is_template():
    with patch(
        "app.integrations.ragflow_llm_template.resolve_template_tenant_id",
        return_value="same-id",
    ):
        assert sync_tenant_llm_from_template("same-id") is False


def test_sync_replaces_llm_rows():
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
    assert len(calls) == 3
    assert "UPDATE tenant" in calls[0]
    assert "DELETE FROM tenant_llm" in calls[1]
    assert "INSERT INTO tenant_llm" in calls[2]
    assert "admin-id" in calls[2]
    assert "user-id" in calls[2]


def test_ensure_shared_llm_config_noop_without_user_id():
    assert ensure_shared_llm_config(None) is False


def test_sync_all_tenant_llm_configs_deduplicates_links():
    db = MagicMock()
    link_a = MagicMock(ragflow_user_id="uid-1")
    link_b = MagicMock(ragflow_user_id="uid-1")
    db.scalars.return_value.all.return_value = [link_a, link_b]

    with patch(
        "app.integrations.ragflow_llm_template.sync_tenant_llm_from_template",
        return_value=True,
    ) as sync:
        count = sync_all_tenant_llm_configs(db)

    assert count == 1
    sync.assert_called_once_with("uid-1", db=db)
