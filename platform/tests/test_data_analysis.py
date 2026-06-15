"""数据分析 — 插件注册与代码校验。"""

from __future__ import annotations

import io
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.features.registry import ensure_plugins_loaded, get_plugin
from app.integrations.data_analysis_executor import validate_user_code
from app.services import data_analysis_store as store
from app.services.data_analysis_profile import (
    missing_data_analysis_modules,
    profile_summary_for_llm,
)


def test_data_analysis_plugin_registered():
    ensure_plugins_loaded()
    plugin = get_plugin("data_analysis")
    assert plugin is not None
    assert plugin.route == "/system/data-analysis"
    assert plugin.permission_code == "feature.data_analysis"
    assert plugin.category == "tools"


def test_profile_summary_for_llm_uses_structure_only():
    profile = {
        "filename": "demo.xlsx",
        "active_sheet": "Sheet1",
        "sheets": [
            {
                "name": "Sheet1",
                "rows": 100,
                "columns": 2,
                "column_profiles": [
                    {
                        "name": "amount",
                        "dtype": "float64",
                        "null_count": 0,
                        "sample_values": ["1.0", "2.0"],
                        "min_value": "1.0",
                        "max_value": "9.0",
                        "mean_value": "5.0",
                    }
                ],
                "sample_rows": [["2024-01", "100"]],
            }
        ],
    }
    text = profile_summary_for_llm(profile)
    assert "demo.xlsx" in text
    assert "amount" in text
    assert "df" in text
    assert "DATA_PATH" in text


def test_profile_summary_for_llm_csv():
    profile = {
        "filename": "demo.csv",
        "file_type": "csv",
        "active_sheet": "data",
        "sheets": [
            {
                "name": "data",
                "rows": 50,
                "columns": 2,
                "column_profiles": [{"name": "sales", "dtype": "int64", "null_count": 0}],
                "sample_rows": [["100"]],
            }
        ],
    }
    text = profile_summary_for_llm(profile)
    assert "CSV" in text
    assert "FILE_TYPE='csv'" in text


def test_data_analysis_deps_available_in_test_env():
    assert missing_data_analysis_modules() == []


def test_validate_user_code_blocks_open():
    with pytest.raises(Exception):
        validate_user_code("open('/etc/passwd')")


def test_apply_matplotlib_cjk_rcparams_does_not_crash():
    mpl = pytest.importorskip("matplotlib")
    pytest.importorskip("matplotlib.pyplot")
    from app.integrations.matplotlib_cjk import apply_matplotlib_cjk_rcparams

    apply_matplotlib_cjk_rcparams()
    assert mpl.rcParams["axes.unicode_minus"] is False


def test_save_session_serializes_uuid_user_id(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_storage_root", lambda: tmp_path)
    user_id = uuid.uuid4()
    session_id = store.new_session_id()
    state = store.create_session_state(
        user_id=user_id,
        session_id=session_id,
        dataset_id="ds1",
        profile={"filename": "demo.csv", "active_sheet": "data", "sheets": []},
    )
    store.save_session(user_id, session_id, state)
    loaded = store.load_session(user_id, session_id)
    assert loaded is not None
    assert loaded["user_id"] == str(user_id)
    json.dumps(loaded)


def test_upload_and_create_session(client: TestClient, admin_token: str, tmp_path, monkeypatch):
    pd = pytest.importorskip("pandas")
    monkeypatch.setattr(store, "_storage_root", lambda: tmp_path)

    buf = io.BytesIO()
    pd.DataFrame({"month": ["2024-01"], "sales": [100]}).to_excel(buf, index=False)
    buf.seek(0)

    upload = client.post(
        "/api/v1/data-analysis/datasets/upload",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("demo.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert upload.status_code == 200, upload.text
    dataset_id = upload.json()["data"]["dataset_id"]

    session = client.post(
        "/api/v1/data-analysis/sessions",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"dataset_id": dataset_id},
    )
    assert session.status_code == 200, session.text
    body = session.json()["data"]
    assert body["dataset_id"] == dataset_id
    assert body["profile"]["filename"] == "demo.xlsx"


def test_create_manual_cell(client: TestClient, admin_token: str, tmp_path, monkeypatch):
    pd = pytest.importorskip("pandas")
    monkeypatch.setattr(store, "_storage_root", lambda: tmp_path)

    buf = io.BytesIO()
    pd.DataFrame({"month": ["2024-01"], "sales": [100]}).to_excel(buf, index=False)
    buf.seek(0)

    upload = client.post(
        "/api/v1/data-analysis/datasets/upload",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("demo.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert upload.status_code == 200, upload.text
    dataset_id = upload.json()["data"]["dataset_id"]

    session = client.post(
        "/api/v1/data-analysis/sessions",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"dataset_id": dataset_id},
    )
    assert session.status_code == 200, session.text
    session_id = session.json()["data"]["session_id"]

    created = client.post(
        f"/api/v1/data-analysis/sessions/{session_id}/cells",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "手动统计"},
    )
    assert created.status_code == 200, created.text
    cell = created.json()["data"]["cell"]
    assert cell["title"] == "手动统计"
    assert "df.head()" in cell["code"]
    assert cell["status"] == "idle"


def test_data_analysis_meta_lists_builtin_libraries(client: TestClient, admin_token: str):
    resp = client.get(
        "/api/v1/data-analysis/meta",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert "pandas" in data["builtin_libraries"]
    assert "seaborn" in data["builtin_libraries"]
    assert "df" in data["builtin_variables"]
