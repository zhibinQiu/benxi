"""系统智能体注册表 — 内置专精智能体，不支持手动创建。

路由描述见 app/core/agents.md；运行时正文见 AGENT.md。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.tool_skill_taxonomy import AGENT_DEFAULT_SKILLS


@dataclass(frozen=True, slots=True)
class AgentProfileDef:
    id: str
    title: str
    description: str
    default_skill_names: tuple[str, ...] = ()
    skills_configurable: bool = True
    sort_order: int = 0


def _skills_for(agent_id: str, *extra: str) -> tuple[str, ...]:
    base = AGENT_DEFAULT_SKILLS.get(agent_id, ())
    merged: list[str] = []
    seen: set[str] = set()
    for name in (*base, *extra):
        if name and name not in seen:
            seen.add(name)
            merged.append(name)
    return tuple(merged)


AGENT_PROFILES: tuple[AgentProfileDef, ...] = (
    AgentProfileDef(
        id="orchestrator",
        title="小析",
        description="通用智能体：处理大多数日常任务——联网/知识库/图谱检索、AI对话/生图/识图、图表绘制。"
        "仅在需要领域专精操作（平台数据CRUD、浏览器自动化、定时通知、Skill开发、长报告撰写）时路由到对应专精。",
        skills_configurable=False,
        sort_order=0,
    ),
    AgentProfileDef(
        id="platform",
        title="平台信息",
        description="文档库CRUD、待办、系统通知、用户与部门管理等平台内真实数据查询与写操作。",
        default_skill_names=_skills_for("platform"),
        sort_order=10,
    ),
    AgentProfileDef(
        id="rpa",
        title="浏览器自动化",
        description="无头浏览器：网页导航、搜索填表、点击截图、流程录制与回放。以浏览器操作为目的，非 Skill 开发调研。",
        default_skill_names=_skills_for("rpa"),
        sort_order=30,
    ),
    AgentProfileDef(
        id="scheduler",
        title="时间调度",
        description="延迟/定时提醒与定时浏览器流程安排，非立即执行类任务。",
        default_skill_names=_skills_for("scheduler"),
        sort_order=40,
    ),
    AgentProfileDef(
        id="skill-dev",
        title="技能开发",
        description="上传型 Skill 生命周期管理（create/update/delete/run_skill_script/list）。"
        "浏览器仅作为创建抓取类 Skill 时的页面调研中间步骤。",
        default_skill_names=_skills_for("skill-dev"),
        sort_order=50,
    ),
)

AGENT_PROFILE_BY_ID: dict[str, AgentProfileDef] = {
    profile.id: profile for profile in AGENT_PROFILES
}

_SPECIALIST_AGENT_IDS = frozenset(
    profile.id for profile in AGENT_PROFILES if profile.id != "orchestrator"
)


def get_agent_profile(agent_id: str) -> AgentProfileDef | None:
    return AGENT_PROFILE_BY_ID.get((agent_id or "").strip())


def resolve_agent_title(agent_id: str) -> str:
    """返回智能体展示标题；未知 id 时回退为 id 本身。"""
    profile = get_agent_profile(agent_id)
    return profile.title if profile else (agent_id or "").strip()
