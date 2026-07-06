"""mermaid-diagram 启动种子与图表规划规则测试。"""

from __future__ import annotations

from sqlalchemy import select

from app.core.phone import bootstrap_login_id
from app.database import SessionLocal
from app.models.agent_skill import AgentSkill
from app.models.org import User
from app.core.report_skill_catalog import REPORT_SKILL_SURVEY
from app.services.agent_planner import _rule_plan_for_diagram, _rule_plan_for_report
from app.services.agent_skill_bootstrap import (
    ensure_mermaid_diagram_skill,
    ensure_report_type_skills,
)
from app.services.agent_skill_router import MERMAID_DIAGRAM_SKILL


def _admin_user(db) -> User:
    user = db.scalar(select(User).where(User.phone == bootstrap_login_id()))
    assert user is not None
    return user


def test_ensure_mermaid_diagram_skill_seeds_from_examples():
    db = SessionLocal()
    try:
        existing = db.scalar(
            select(AgentSkill).where(AgentSkill.name == MERMAID_DIAGRAM_SKILL)
        )
        if existing:
            db.delete(existing)
            db.commit()
        assert ensure_mermaid_diagram_skill(db) is True
        row = db.scalar(
            select(AgentSkill).where(AgentSkill.name == MERMAID_DIAGRAM_SKILL)
        )
        assert row is not None
        assert row.enabled is True
    finally:
        db.close()


def test_rule_plan_for_diagram_mindmap():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        ensure_mermaid_diagram_skill(db)
        plan = _rule_plan_for_diagram(
            db,
            user,
            "帮我生成把大象装进冰箱的思维导图",
        )
        assert plan is not None
        assert plan.uploaded_skill == MERMAID_DIAGRAM_SKILL
        assert plan.direct_answer is False
    finally:
        db.close()


def test_ensure_report_type_skills_seeds():
    db = SessionLocal()
    try:
        count = ensure_report_type_skills(db)
        assert count >= 1
        row = db.scalar(
            select(AgentSkill).where(AgentSkill.name == REPORT_SKILL_SURVEY)
        )
        assert row is not None
        assert row.enabled is True
    finally:
        db.close()


def test_rule_plan_for_report_survey():
    db = SessionLocal()
    try:
        user = _admin_user(db)
        ensure_report_type_skills(db)
        plan = _rule_plan_for_report(
            db,
            user,
            "请撰写一份新能源汽车行业调研报告",
        )
        assert plan is not None
        assert plan.uploaded_skill == REPORT_SKILL_SURVEY
        assert "knowledge_retrieve" in plan.atomic_tools
        assert "web_search" in plan.atomic_tools
    finally:
        db.close()
