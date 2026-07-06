"""Skill 匹配度评估与能力兜底测试。"""

from __future__ import annotations

from sqlalchemy import select

from app.core.phone import bootstrap_login_id
from app.database import SessionLocal
from app.models.org import User
from app.services.agent_capability_fallback import (
    MISSING_CAPABILITY_CODE,
    build_missing_capability_receipt,
)
from app.services.agent_skill_match import assess_skill_match


def _admin_user(db) -> User:
    user = db.scalar(select(User).where(User.phone == bootstrap_login_id()))
    assert user is not None
    return user


def test_assess_skill_match_chitchat_like_low_score():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        assessment = assess_skill_match(db, user, "你好")
        assert assessment.kind in ("none", "weak")
        assert assessment.max_similarity < 0.3
    finally:
        db.close()


def test_assess_skill_match_research_question():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        assessment = assess_skill_match(db, user, "全国碳市场最新政策有哪些？")
        assert assessment.kind == "full"
        assert assessment.agent_scores
    finally:
        db.close()


def test_missing_capability_receipt_shape():
    receipt = build_missing_capability_receipt(
        "生成 AI 数字人宣传视频",
        missing_capability=("数字人视频生成",),
        supported_capability=("数据查询", "文档生成"),
        match_kind="none",
        max_similarity=0.0,
    )
    assert receipt["success"] is False
    assert receipt["code"] == MISSING_CAPABILITY_CODE
    assert "数字人" in receipt["detail"]["user_demand"]
