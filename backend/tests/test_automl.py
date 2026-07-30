"""自动化机器学习 — 插件注册与 CSV 画像。"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.features.registry import ensure_plugins_loaded, get_plugin
from app.services import automl_service as svc
from app.services.automl_runner import list_models_for_task, pycaret_available


def test_auto_ml_plugin_registered():
    ensure_plugins_loaded()
    plugin = get_plugin("auto_ml")
    assert plugin is not None
    assert plugin.route == "/system/auto-ml"
    assert plugin.permission_code == "feature.auto_ml"
    assert plugin.router is not None


def test_auto_ml_model_catalog():
    assert len(list_models_for_task("classification")) >= 5
    assert len(list_models_for_task("anomaly")) >= 3
    assert list_models_for_task("unknown") == []


def test_auto_ml_meta_without_requiring_pycaret():
    meta = svc.get_meta()
    assert meta.max_file_mb >= 1
    assert ".csv" in meta.accepted_extensions
    assert len(meta.task_types) == 5
    assert meta.configured is pycaret_available()
    if not meta.configured:
        assert meta.service_hint


def test_auto_ml_upload_and_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOML_STORAGE_DIR", str(tmp_path / "automl"))
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        csv = b"a,b,label\n1,2,0\n3,4,1\n5,6,0\n"
        out = svc.upload_dataset(user_id="test-user", filename="demo.csv", content=csv)
        assert out.dataset_id
        assert out.profile.rows == 3
        assert out.profile.columns == 3
        assert [c.name for c in out.profile.column_profiles] == ["a", "b", "label"]

        again = svc.get_dataset(user_id="test-user", dataset_id=out.dataset_id)
        assert again.profile.filename == "demo.csv"
    finally:
        get_settings.cache_clear()


def test_auto_ml_rejects_non_csv():
    with pytest.raises(Exception) as ei:
        svc.upload_dataset(user_id="u", filename="x.xlsx", content=b"1,2\n")
    assert "CSV" in str(ei.value.detail if hasattr(ei.value, "detail") else ei.value)


def test_auto_ml_meta_api(client: TestClient, admin_token: str):
    res = client.get(
        "/api/v1/auto-ml/meta",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert "configured" in data
    assert data["accepted_extensions"] == [".csv"]
    assert len(data["task_types"]) == 5
