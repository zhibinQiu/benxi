"""路由诊断测试 — 展示每一步的决策过程。

运行方式:
    cd backend && python -m pytest tests/test_routing_diagnostic.py -v -s --no-header -q

-s 参数确保 stdout 中打印的步骤能实时显示。
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.models.org import User
from app.services.agent_route_resolver import resolve_agent_route, resolve_agent_routes
from app.services.agent_intent import (
    has_explicit_specialist_intent,
    is_chitchat_message,
    should_orchestrator_reply_directly,
)
from app.services.agent_skill_router import (
    is_diagram_generation_message,
    is_skill_management_message,
    matches_browser_intent,
    matches_scheduler_intent,
)


def _admin_user(db) -> User:
    user = db.scalar(select(User).limit(1))
    assert user is not None
    return user


TEST_CASES = [
    {
        "name": "用例1-流程图",
        "message": "帮我绘制把大象装进冰箱的流程图",
        "expect_agent": "orchestrator",
    },
    {
        "name": "用例2-技能使用",
        "message": "请使用 zhangxuefeng-skill 技能：你是谁？",
        "expect_agent": "orchestrator",
    },
    {
        "name": "用例3-定时提醒",
        "message": "8s 后提醒我喝水",
        "expect_agent": "orchestrator",
    },
    {
        "name": "用例4-生成技能",
        "message": "生成一个 skill，帮我从https://www.tanshichang.cn 爬取最新的碳市场价格",
        "expect_agent": "skill-dev",
    },
]


def test_signal_detection():
    """测试用例 4 个消息的各个信号检测结果。"""
    print("\n" + "=" * 70)
    print("📊 信号检测结果")
    print("=" * 70)
    for case in TEST_CASES:
        msg = case["message"]
        print(f"\n── {case['name']}: \"{msg[:50]}...\" ──")
        print(f"  is_chitchat:                {is_chitchat_message(msg)}")
        print(f"  is_diagram:                 {is_diagram_generation_message(msg)}")
        print(f"  is_skill_management:        {is_skill_management_message(msg)}")
        print(f"  matches_scheduler:          {matches_scheduler_intent(msg)}")
        print(f"  matches_browser:            {matches_browser_intent(msg)}")
        print(f"  has_explicit_specialist:    {has_explicit_specialist_intent(msg)}")
        print(f"  should_orchestrator_direct: {should_orchestrator_reply_directly(msg)}")


@pytest.mark.parametrize(
    "case",
    TEST_CASES,
    ids=[c["name"] for c in TEST_CASES],
)
def test_routing_diagnostic(case):
    """逐个测试路由决策过程。"""
    name = case["name"]
    msg = case["message"]
    expected = case["expect_agent"]

    print(f"\n{'#'*70}")
    print(f"# 🧪 {name}")
    print(f"#    消息: \"{msg}\"")
    print(f"#    预期路由: {expected}")
    print(f"{'#'*70}")

    db = SessionLocal()
    try:
        user = _admin_user(db)
        route = resolve_agent_route(db, user, msg)
        print(f"\n✅ 最终路由: agent={route.agent_id}, reason=\"{route.reason}\"")
        assert route.agent_id == expected, (
            f"预期路由到 {expected}，实际路由到 {route.agent_id} (reason: {route.reason})"
        )
    finally:
        db.close()
