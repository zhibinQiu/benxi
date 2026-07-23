"""知识图谱平台数据全量同步：已删除的平台对象应从图谱清除。"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select

from app.database import SessionLocal
from app.models.kg import KgEntity, KgEntityType, KgRelationType
from app.models.org import Department, User
from app.services.kg_system_sync_service import (
    DEPT_ID_PROP,
    USER_ID_PROP,
    sync_platform_org_to_kg,
)


def _ensure_org_person_types(db) -> dict[str, uuid.UUID]:
    codes: dict[str, uuid.UUID] = {}
    for code, label in (("org", "组织"), ("person", "人员")):
        row = db.scalar(select(KgEntityType).where(KgEntityType.code == code))
        if not row:
            row = KgEntityType(code=code, label=label, description="")
            db.add(row)
            db.flush()
        codes[code] = row.id
    for code, label in (("contains", "包含"), ("employs", "雇佣")):
        if not db.scalar(select(KgRelationType).where(KgRelationType.code == code)):
            db.add(KgRelationType(code=code, label=label, description=""))
    db.flush()
    return codes


def test_sync_platform_org_removes_deleted_user_entity(admin_token: str):
    """全量组织同步应删除平台侧已不存在用户对应的 person 实体。"""
    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.phone == "admin"))
        assert admin is not None
        types = _ensure_org_person_types(db)

        orphan = KgEntity(
            type_id=types["person"],
            name="已删除用户幽灵",
            description="应被全量同步清除",
            properties={USER_ID_PROP: str(uuid.uuid4())},
            owner_id=admin.id,
            created_by=admin.id,
            scope="company",
        )
        db.add(orphan)
        db.commit()
        orphan_id = orphan.id

        stats = sync_platform_org_to_kg(db, admin)
        db.commit()

        assert stats["deleted"] >= 1
        assert db.scalar(select(KgEntity).where(KgEntity.id == orphan_id)) is None
    finally:
        db.close()


def test_sync_platform_org_removes_deleted_department_entity(admin_token: str):
    """全量组织同步应删除平台侧已不存在的部门对应 org 实体。"""
    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.phone == "admin"))
        assert admin is not None
        types = _ensure_org_person_types(db)
        assert db.scalar(select(Department.id).limit(1)) is not None

        orphan = KgEntity(
            type_id=types["org"],
            name="已删除部门幽灵",
            description="应被全量同步清除",
            properties={DEPT_ID_PROP: str(uuid.uuid4())},
            owner_id=admin.id,
            created_by=admin.id,
            scope="company",
        )
        db.add(orphan)
        db.commit()
        orphan_id = orphan.id

        stats = sync_platform_org_to_kg(db, admin)
        db.commit()

        assert stats["deleted"] >= 1
        assert db.scalar(select(KgEntity).where(KgEntity.id == orphan_id)) is None
    finally:
        db.close()


def test_neo4j_prune_helper_deletes_not_in_allowed():
    """Neo4j 全量同步的 prune 助手应按允许集合构造删除查询。"""
    import asyncio

    from app.services.kg_service import KgService

    async def _run():
        svc = KgService(MagicMock())
        svc.run_single = AsyncMock(return_value={"deleted": 3})
        n = await svc._prune_entities_not_in(
            prop_key="platform_user_id",
            allowed_values=["keep-1"],
        )
        assert n == 3
        query = svc.run_single.await_args.args[0]
        params = svc.run_single.await_args.kwargs["params"]
        assert "platform_user_id" in query
        assert "DETACH DELETE" in query
        assert params["allowed"] == ["keep-1"]

    asyncio.run(_run())
