"""系统智能体注册表 — 内置专精智能体，不支持手动创建。"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.report_skill_catalog import REPORT_SKILL_NAMES
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
        description=(
            "仅用于寒暄、简单心算/常识问答、或无需任何专精工具的单轮闲聊；"
            "不处理数据查询、Skill 执行、文档操作、检索调研——上述必须转交对应专精智能体"
        ),
        skills_configurable=False,
        sort_order=0,
    ),
    AgentProfileDef(
        id="platform",
        title="平台操作",
        description=(
            "用户要操作或查询平台内系统数据：文档库/文件夹/上传分享、待办、通知提醒、"
            "用户列表/部门/组织架构（list_users、list_departments、kg_query 等）；"
            "不是知识库正文调研，也不是执行上传型 Python Skill"
        ),
        tool_categories=(
            ToolCategory.DOCUMENT,
            ToolCategory.PLATFORM,
            ToolCategory.ADMIN,
            ToolCategory.GRAPH,
        ),
        sort_order=10,
    ),
    AgentProfileDef(
        id="research",
        title="检索研究",
        description=(
            "用户要从企业知识库文档正文、联网搜索、本体图谱做调研与综合问答；"
            "典型：政策解读、行业动态、文档内容摘要；"
            "不创建/修改 Skill，不执行用户上传的 Python 脚本 Skill，不查用户/部门系统名单"
        ),
        tool_categories=(ToolCategory.WEB, ToolCategory.KNOWLEDGE, ToolCategory.GRAPH),
        tool_names=("search_documents_by_name",),
        default_skill_names=(
            "web-search",
            "knowledge-search",
            "kg-palantir",
            "knowledge-research",
        ),
        sort_order=20,
    ),
    AgentProfileDef(
        id="report",
        title="报告撰写",
        description=(
            "用户要撰写可研、需求分析、建设方案、调研、测试报告或工作计划等结构化长文；"
            "先 load 对应报告 Skill，再检索材料并按模板输出 Markdown 长报告"
        ),
        tool_categories=(ToolCategory.WEB, ToolCategory.KNOWLEDGE),
        default_skill_names=REPORT_SKILL_NAMES,
        sort_order=21,
    ),
    AgentProfileDef(
        id="diagram",
        title="生图",
        description=(
            "用户要生成思维导图、流程图、时序图、状态图或 Mermaid 图表（回复中含 ```mermaid 围栏）"
        ),
        default_skill_names=("mermaid-diagram",),
        sort_order=25,
    ),
    AgentProfileDef(
        id="rpa",
        title="浏览器 RPA",
        description=(
            "用户要在网页上导航、点击、填表、截图，或录制/回放浏览器自动化流程；"
            "典型：打开某 URL、页面截图、模拟表单操作"
        ),
        tool_categories=(ToolCategory.BROWSER,),
        sort_order=30,
    ),
    AgentProfileDef(
        id="scheduler",
        title="定时任务",
        description=(
            "用户要设置延迟/定时提醒、取消定时任务，或安排定时执行的浏览器 RPA 流程"
        ),
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
        description=(
            "用户要创建/更新/调试上传型 Skill，或执行已有 Skill 脚本获取数据（run_skill_script）；"
            "含：编写爬虫 Skill、查碳价等自定义脚本、对话上文刚创建的技能、短跟贴如「北京」「广东」查价；"
            "先 list_agent_skills 或阅读 available_skills 目录匹配 slug，再 run/update/create"
        ),
        tool_categories=(ToolCategory.SKILL_MGMT,),
        sort_order=50,
    ),
)

AGENT_PROFILE_BY_ID: dict[str, AgentProfileDef] = {
    profile.id: profile for profile in AGENT_PROFILES
}


def get_agent_profile(agent_id: str) -> AgentProfileDef | None:
    return AGENT_PROFILE_BY_ID.get((agent_id or "").strip())


def resolve_agent_title(agent_id: str) -> str:
    """返回智能体展示标题；未知 id 时回退为 id 本身。"""
    profile = get_agent_profile(agent_id)
    return profile.title if profile else (agent_id or "").strip()
