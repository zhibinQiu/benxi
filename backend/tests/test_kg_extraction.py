"""知识图谱文档自动抽取。"""

from __future__ import annotations

import uuid

from app.services.kg_extraction_service import (
    _normalize_entity_rows,
    _normalize_relation_rows,
    apply_extraction_result,
    apply_extraction_result_from_text,
    extract_json_payload,
)


def test_extract_json_payload_from_codeblock():
    raw = """```json
{"entities": [], "relations": []}
```"""
    data = extract_json_payload(raw)
    assert data == {"entities": [], "relations": []}


def test_normalize_entity_and_relation_rows():
    entities = _normalize_entity_rows(
        {
            "entities": [
                {"type_code": "regulation", "name": "碳市场管理办法", "description": "法规"},
                {"type_code": "bad", "name": "", "description": "skip"},
                {"type_code": "metric", "name": "范围一排放量", "description": ""},
            ]
        }
    )
    assert len(entities) == 2
    relations = _normalize_relation_rows(
        {
            "relations": [
                {
                    "type_code": "constrains",
                    "from_name": "碳市场管理办法",
                    "to_name": "范围一排放量",
                },
                {
                    "type_code": "references",
                    "from_name": "碳市场管理办法",
                    "to_name": "碳市场管理办法",
                },
            ]
        }
    )
    assert len(relations) == 1
    assert relations[0]["type_code"] == "constrains"


def test_apply_extraction_result_creates_entities(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    meta = client.get("/api/v1/kg/meta", headers=headers).json()["data"]
    assert meta["entity_total"] >= 1

    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models.document import Document, DocumentVersion
    from app.models.org import User
    from app.services.kg_extraction_service import apply_extraction_result

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.phone == "admin"))
        assert user is not None
        doc = db.scalar(select(Document).where(Document.deleted_at.is_(None)))
        if not doc:
            return
        version = db.scalar(
            select(DocumentVersion)
            .where(
                DocumentVersion.document_id == doc.id,
                DocumentVersion.file_size > 0,
            )
            .limit(1)
        )
        if not version:
            return

        stats = apply_extraction_result(
            db,
            user,
            doc,
            version,
            {
                "entities": [
                    {
                        "type_code": "regulation",
                        "name": f"测试法规-{uuid.uuid4().hex[:6]}",
                        "description": "自动抽取测试",
                    }
                ],
                "relations": [],
            },
        )
        db.commit()
        assert stats["entities_created"] == 1
    finally:
        db.close()


def test_apply_extraction_result_from_text_creates_root_and_entities(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    client.get("/api/v1/kg/meta", headers=headers)

    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models.org import User

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.phone == "admin"))
        assert user is not None
        suffix = uuid.uuid4().hex[:6]
        stats = apply_extraction_result_from_text(
            db,
            user,
            title=f"测试会议-{suffix}",
            data={
                "entities": [
                    {
                        "type_code": "person",
                        "name": f"参会人-{suffix}",
                        "description": "会议抽取测试",
                    }
                ],
                "relations": [],
            },
            source_type="meeting_summary",
        )
        db.commit()
        assert stats["entities_created"] == 1
        assert stats["root_entity_id"]
    finally:
        db.close()


def test_kg_extract_batch_api_no_documents(client, admin_token, monkeypatch):
    headers = {"Authorization": f"Bearer {admin_token}"}
    client.get("/api/v1/kg/meta", headers=headers)

    from app.services import kg_extraction_service
    from app.services.kg_extraction_service import ExtractionTargetPlan

    monkeypatch.setattr(
        kg_extraction_service,
        "collect_extraction_targets",
        lambda db, user, *, scope, force=False: ExtractionTargetPlan(
            pending=[],
            already_extracted_count=0,
            total_candidates=0,
        ),
    )

    res = client.post(
        "/api/v1/kg/extract/batch",
        headers=headers,
        json={"scope": "knowledge", "force": False},
    )
    assert res.status_code == 400
    assert "没有可抽离" in res.json()["message"]


def test_kg_extract_batch_api_all_extracted(client, admin_token, monkeypatch):
    headers = {"Authorization": f"Bearer {admin_token}"}
    client.get("/api/v1/kg/meta", headers=headers)

    from app.services import kg_extraction_service
    from app.services.kg_extraction_service import ExtractionTargetPlan

    monkeypatch.setattr(
        kg_extraction_service,
        "collect_extraction_targets",
        lambda db, user, *, scope, force=False: ExtractionTargetPlan(
            pending=[],
            already_extracted_count=5,
            total_candidates=5,
        ),
    )

    res = client.post(
        "/api/v1/kg/extract/batch",
        headers=headers,
        json={"scope": "knowledge", "force": False},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["queued"] is False
    assert data["reason"] == "all_extracted"
    assert data["already_extracted_count"] == 5


def test_collect_extraction_targets_skips_marked_documents(
    client, admin_token, monkeypatch
):
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models.document import Document, DocumentVersion
    from app.models.org import User
    from app.services.kg_extraction_service import (
        apply_extraction_result,
        collect_extraction_targets,
    )

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.phone == "admin"))
        assert user is not None
        doc = db.scalar(select(Document).where(Document.deleted_at.is_(None)))
        if not doc:
            return
        version = db.scalar(
            select(DocumentVersion)
            .where(
                DocumentVersion.document_id == doc.id,
                DocumentVersion.file_size > 0,
            )
            .limit(1)
        )
        if not version:
            return

        apply_extraction_result(
            db,
            user,
            doc,
            version,
            {"entities": [], "relations": []},
        )
        db.commit()

        monkeypatch.setattr(
            "app.services.documents.listing.list_queryable_documents",
            lambda db, user, *, page, page_size, keyword=None: (
                ([doc], 1) if page == 1 else ([], 0)
            ),
        )

        plan = collect_extraction_targets(db, user, scope="platform", force=False)
        assert plan.pending == []
        assert plan.already_extracted_count == 1
        assert plan.total_candidates == 1

        plan_force = collect_extraction_targets(db, user, scope="platform", force=True)
        assert len(plan_force.pending) == 1
    finally:
        db.close()


def test_kg_extract_batch_api_queues(client, admin_token, monkeypatch):
    headers = {"Authorization": f"Bearer {admin_token}"}
    client.get("/api/v1/kg/meta", headers=headers)

    monkeypatch.setattr(
        "app.api.kg.schedule_kg_batch_extraction",
        lambda db, user, *, scope, force=False: {
            "queued": True,
            "scope": scope,
            "document_count": 1,
            "already_extracted_count": 2,
            "total_candidates": 3,
        },
    )

    res = client.post(
        "/api/v1/kg/extract/batch",
        headers=headers,
        json={"scope": "platform", "force": False},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["queued"] is True
    assert data["scope"] == "platform"
    assert data["document_count"] == 1


def test_kg_extract_from_text_api(client, admin_token, monkeypatch):
    headers = {"Authorization": f"Bearer {admin_token}"}
    client.get("/api/v1/kg/meta", headers=headers)

    from app.services import kg_extraction_service

    def fake_call_llm_extract(*, document_title: str, text: str):
        return {
            "entities": [
                {
                    "type_code": "project",
                    "name": f"API会议项目-{uuid.uuid4().hex[:6]}",
                    "description": "接口测试",
                }
            ],
            "relations": [],
        }

    monkeypatch.setattr(kg_extraction_service, "_call_llm_extract", fake_call_llm_extract)

    res = client.post(
        "/api/v1/kg/extract-from-text",
        headers=headers,
        json={
            "title": "接口测试会议",
            "text": "本次会议讨论了碳市场管理办法与减排项目推进计划，并明确了各部门职责分工与后续里程碑。",
        },
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["skipped"] is False
    assert data["entities_created"] >= 1
    assert data["root_entity_id"]
