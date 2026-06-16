"""知识图谱文档自动抽取。"""

from __future__ import annotations

import uuid

from app.services.kg_extraction_service import (
    _normalize_entity_rows,
    _normalize_relation_rows,
    apply_extraction_result,
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
