"""系统智能体注册表 — 内置专精智能体，不支持手动创建。"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.agent_tool_registry import ToolCategory


@dataclass(frozen=True)
class AgentProfileDef:
    id: str
    title: str
    description: str
    tool_categories: tuple[ToolCategory, ...] = ()
    tool_names: tuple[str, ...] = ()
    default_skill_names: tuple[str, ...] = ()
    skills_configurable: bool = True
    sort_order: int = 0


AGENT_PROFILES: tuple[AgentProfileDef, ...] = (
    AgentProfileDef(
        id="orchestrator",
        title="小析调度",
        description="日常寒暄、简单计算或无需专精工具的单轮问答时使用",
        skills_configurable=False,
        sort_order=0,
    ),
    AgentProfileDef(
        id="platform",
        title="平台操作",
        description="用户要查/管平台文档库、待办事项或发送即时通知时使用",
        tool_categories=(ToolCategory.DOCUMENT, ToolCategory.PLATFORM),
        sort_order=10,
    ),
    AgentProfileDef(
        id="research",
        title="检索研究",
        description="用户要查企业文档、联网资讯、本体图谱或综合检索材料时使用",
        tool_categories=(ToolCategory.WEB, ToolCategory.KNOWLEDGE, ToolCategory.GRAPH),
        default_skill_names=(
            "web-search",
            "knowledge-search",
            "kg-palantir",
            "knowledge-research",
        ),
        sort_order=20,
    ),
    AgentProfileDef(
        id="rpa",
        title="浏览器 RPA",
        description="用户要在网页上导航、点击、填表、截图或录制/回放浏览器流程时使用",
        tool_categories=(ToolCategory.BROWSER,),
        sort_order=30,
    ),
    AgentProfileDef(
        id="scheduler",
        title="定时任务",
        description="用户要设置延迟/定时提醒、取消定时任务或安排定时 RPA 时使用",
        tool_names=(
            "schedule_notification",
            "list_scheduled_notifications",
            "cancel_scheduled_notification",
            "schedule_browser_workflow",
        ),
        sort_order=40,
    ),
    AgentProfileDef(
        id="skill-dev",
        title="技能开发",
        description="用户要创建、更新、调试上传型技能或修复技能脚本时使用",
        tool_categories=(ToolCategory.SKILL_MGMT,),
        sort_order=50,
    ),
)

AGENT_PROFILE_BY_ID: dict[str, AgentProfileDef] = {
    profile.id: profile for profile in AGENT_PROFILES
}


def get_agent_profile(agent_id: str) -> AgentProfileDef | None:
    return AGENT_PROFILE_BY_ID.get((agent_id or "").strip())
