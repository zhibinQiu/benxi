"""发展技能 slug 冲突时自动重命名。"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.database import SessionLocal
from app.models.agent_skill import AgentSkill
from app.models.org import User
from app.services.agent_skill_service import allocate_unique_skill_slug, create_generated_skill


def _any_user(db) -> User:
    user = db.scalar(select(User).limit(1))
    assert user is not None
    return user


def test_allocate_unique_skill_slug_appends_suffix():
    db = SessionLocal()
    base = f"test-auto-rename-{uuid.uuid4().hex[:8]}"
    try:
        user = _any_user(db)
        create_generated_skill(
            db,
            user,
            name=base,
            description="first",
            skill_md_body="body",
        )
        assert allocate_unique_skill_slug(db, base) == f"{base}-2"
        create_generated_skill(
            db,
            user,
            name=f"{base}-2",
            description="second",
            skill_md_body="body",
        )
        assert allocate_unique_skill_slug(db, base) == f"{base}-3"
    finally:
        for row in db.scalars(select(AgentSkill).where(AgentSkill.name.like(f"{base}%"))):
            db.delete(row)
        db.commit()
        db.close()


def test_create_generated_skill_auto_renames_on_conflict():
    db = SessionLocal()
    base = f"test-create-rename-{uuid.uuid4().hex[:8]}"
    try:
        user = _any_user(db)
        first = create_generated_skill(
            db,
            user,
            name=base,
            description="first",
            skill_md_body="body",
        )
        assert first.name == base
        second = create_generated_skill(
            db,
            user,
            name=base,
            description="second",
            skill_md_body="body",
        )
        assert second.name == f"{base}-2"
    finally:
        for row in db.scalars(select(AgentSkill).where(AgentSkill.name.like(f"{base}%"))):
            db.delete(row)
        db.commit()
        db.close()
