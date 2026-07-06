"""统一任务流 — 分析阶段。"""

from app.services.agent_intent import plan_agent_tools
from app.services.agent_task_flow import derive_task_analysis


def test_derive_task_analysis_for_reminder_like_message():
    intent = plan_agent_tools(
        "8s 后提醒我喝水",
        attach_count=0,
    )
    analysis = derive_task_analysis(
        "8s 后提醒我喝水",
        intent_plan=intent,
    )
    assert analysis.user_goal == "8s 后提醒我喝水"
    assert analysis.intent == "处理用户请求"


def test_derive_task_analysis_for_attachment():
    intent = plan_agent_tools(
        "总结附件",
        attach_count=1,
    )
    analysis = derive_task_analysis("总结附件", intent_plan=intent)
    assert "附件" in analysis.summary
