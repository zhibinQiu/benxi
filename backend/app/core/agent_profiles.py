"""系统智能体注册表 — 内置专精智能体，不支持手动创建。

路由描述见 app/core/agents.md；运行时正文见 AGENT.md。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.report_skill_catalog import REPORT_SKILL_NAMES
from app.core.tool_skill_taxonomy import AGENT_DEFAULT_SKILLS, DEFAULT_AGENT_TOOLS


@dataclass(frozen=True, slots=True)
class AgentProfileDef:
    id: str
    title: str
    description: str
    default_skill_names: tuple[str, ...] = ()
    default_runtime_tool_names: tuple[str, ...] = ()
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


def _tools_for(agent_id: str) -> tuple[str, ...]:
    return DEFAULT_AGENT_TOOLS.get(agent_id, ())


AGENT_PROFILES: tuple[AgentProfileDef, ...] = (
    AgentProfileDef(
        id="orchestrator",
        title="小析",
        description="调度智能体：负责任务理解、分配与验收。可见已挂载工具/技能并编排；"
        "执行委托子智能体或路由专精 Agent。",
        default_runtime_tool_names=_tools_for("orchestrator"),
        skills_configurable=True,
        sort_order=0,
    ),
    AgentProfileDef(
        id="platform",
        title="平台操作",
        description="文档库CRUD、待办、系统通知、用户与部门管理等平台内真实数据查询与写操作。",
        default_skill_names=_skills_for("platform"),
        default_runtime_tool_names=_tools_for("platform"),
        sort_order=10,
    ),
    AgentProfileDef(
        id="report",
        title="报告撰写",
        description="撰写可研、需求分析、建设方案、调研、测试报告或工作计划等结构化长文；"
        "同时检索企业知识库与联网资讯，按模版输出 Markdown 长报告。",
        default_skill_names=REPORT_SKILL_NAMES,
        default_runtime_tool_names=_tools_for("report"),
        skills_configurable=True,
        sort_order=21,
    ),
    AgentProfileDef(
        id="skill-dev",
        title="技能开发",
        description="上传型 Skill 生命周期管理（create/update/delete/run_skill_script/list）。"
        "浏览器仅作为创建抓取类 Skill 时的页面调研中间步骤。",
        default_skill_names=_skills_for("skill-dev"),
        default_runtime_tool_names=_tools_for("skill-dev"),
        sort_order=50,
    ),
    AgentProfileDef(
        id="carbon",
        title="双碳智能体",
        description="双碳领域：碳市场行情、碳交易、碳中和/碳达峰政策、CCER、碳排放核算、行业减排路径等所有双碳相关问题。",
        default_skill_names=_skills_for("carbon"),
        default_runtime_tool_names=_tools_for("carbon"),
        sort_order=40,
    ),
    AgentProfileDef(
        id="power-economy",
        title="电力-经济耦合分析",
        description="电力经济领域：电力市场行情/电价/用电数据分析、电力-经济耦合模型与预测、电力体制改革、发电侧经济性、电力规划与供需预测。",
        default_runtime_tool_names=_tools_for("power-economy"),
        skills_configurable=True,
        sort_order=45,
    ),
    AgentProfileDef(
        id="stock",
        title="股市分析",
        description="股市分析领域：个股基本面深度解读、多角色圆桌对抗性研究（含基本面与短线两个研究方向）、量价技术面诊断与决策参考。",
        default_skill_names=_skills_for("stock"),
        default_runtime_tool_names=_tools_for("stock"),
        skills_configurable=True,
        sort_order=47,
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
