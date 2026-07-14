"""智能体信号检测与意图识别 — 用户消息 vs 路由/记忆/平台/Skill 管理的匹配判断。

负责检测用户消息中的语义信号，判断用户意图属于技能管理、图表生成、平台操作、
浏览器/RPA、记忆读写、路由模式（串行/并行）等。
与 agent_skill_routing.py（LLM 路由规划）和 agent_skill_match.py（匹配评分）构成信号层→规划层→评分层。

注意：通用路由信号检测契约在 agentkit_route.signals（SignalDetector Protocol）；
本文件的 regex 是平台绑定实现，不应被 agentkit 依赖。

合并历史：原 agent_routing_signals.py 的路由信号（2026-07）已并入本文件。"""

from __future__ import annotations

import re
from typing import Any

from app.core.agent_loop_state import LoopState

from app.skills.types import SkillSource

# ── 平台绑定信号：URL / 页面 / 图片 ───────────────────────────────
_URL_IN_MESSAGE_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
_DOMAIN_IN_MESSAGE_RE = re.compile(
    r"(?:https?://)?(?:[\w-]+\.)+[a-z]{2,}(?:/[^\s<>\"']*)?", re.I
)
_PAGE_INTENT_RE = re.compile(
    r"页面|网页|网站|链接|url|站点|抓取|爬取|行情|价格|打开.{0,6}看", re.I
)
_SCREENSHOT_INTENT_RE = re.compile(
    r"截图|截屏|screenshot|页面长什么样|可视化.{0,6}页面|看一下.{0,6}(?:网页|页面|网站)", re.I
)

# ── 平台绑定信号：技能管理 ──────────────────────────────────────────
_SKILL_MANAGE_RE = re.compile(
    r"(?:创建|新建|编写|写一个|做一个|生成|更新|修改|删除).{0,16}(?:skill|技能|Skills?)"
    r"|(?:skill|技能|Skills?).{0,10}(?:创建|新建|编写|更新|修改|删除)"
    r"|帮我.{0,8}(?:skill|技能)",
)
_SKILL_INSTRUCTION_ONLY_RE = re.compile(
    r"仅说明|纯指令|不要脚本|不写脚本|无需脚本|instruction.only|"
    r"mermaid|流程图说明|只写.{0,4}说明",
    re.I,
)
_SCRIPT_TASK_RE = re.compile(
    r"爬取|抓取|拉取|脚本|执行|运行|数据|api|自动化|价格|行情|采集|同步|监控",
    re.I,
)

# ── 平台绑定信号：图表 ─────────────────────────────────────────────
_DIAGRAM_INTENT_RE = re.compile(
    r"(思维导图|流程图|时序图|状态图|架构图|关系图|组织结构图|"
    r"mermaid|Mermaid|mindmap|flowchart|sequenceDiagram|stateDiagram|"
    r"画.{0,4}(?:图|流程|导图)|生成.{0,8}(?:图|导图|流程图)|"
    r"绘制.{0,6}(?:图|流程))",
    re.I,
)

# ── 平台绑定信号：记忆 ─────────────────────────────────────────────
_MEMORY_READ_RE = re.compile(
    r"(?:上次|之前|还记得|记住的|以前.{0,4}聊|延续.{0,4}会话|我的偏好)"
)
_MEMORY_WRITE_RE = re.compile(
    r"(?:请记住|帮我记|记下来|以后记得|别忘了)"
)

# ── 平台绑定信号：结论质量 ───────────────────────────────────────────
_INCONCLUSIVE_SKILL_CONCLUSION_RE = re.compile(
    r"无法|失败|未能|不知道|没有结果|无结论|无有效|未获取|未找到|"
    r"请检查|不能完成|超时|timeout|error|exception|traceback",
    re.I,
)

# ── 路由信号：平台操作/调度/浏览器/RPA ───────────────────────────
PLATFORM_OPS_EXTRA_RE = re.compile(
    r"(文档库|文件夹|我的文件|待办|todo|记一下|加个待办|"
    r"list_document|list_library|list_manageable|rename_document|"
    r"move_document|share_document|delete_document|send_notification|"
    r"上传.{0,6}文档|分享.{0,4}文档|重命名|移动到)",
    re.I,
)

SCHEDULER_RE = re.compile(
    r"(定时任务|定时执行|定时提醒|取消定时|列出.*定时|"
    r"schedule_browser|list_scheduled_notifications|cancel_scheduled_notification|"
    r"延迟提醒|cron|"
    r"(?:提醒|通知|叫我).{0,16}后|"
    r"\d+\s*(?:s|sec|秒|分钟?|min|小时?|h).{0,8}后)",
    re.I,
)

BROWSER_RE = re.compile(
    r"(browser_|网页|网站|页面|截图|截屏|workflow|"
    r"browser_navigate|browser_snapshot|browser_click|点击|填表|浏览器自动化|"
    r"打开.{0,4}(?:网页|网站|链接)|"
    r"(?<![\u4e00-\u9fff])RPA(?![\u4e00-\u9fff]))",
    re.I,
)

SEARCH_RPA_TOPIC_RE = re.compile(
    r"(?:搜索|查(?:一下|下)?|检索).{0,16}rpa(?![a-z])|"
    r"rpa(?![a-z]).{0,16}(?:是什么|介绍|趋势|应用|有哪些|资料|信息)",
    re.I,
)

SEARCH_RPA_BROWSER_ACTION_RE = re.compile(
    r"(?:截图|截屏|并(?:截|拍)|网页|浏览器|"
    r"browser_|填表|点击|打开.{0,4}(?:网页|网站|链接)|workflow|录制|回放)",
    re.I,
)

BROWSER_SITE_SEARCH_RE = re.compile(
    r"(?:百度|bing|google|淘宝|京东|搜狗).{0,8}(?:搜索|查|找)|"
    r"(?:搜索|查|找).{0,8}(?:百度|bing|google|淘宝|京东|搜狗)",
    re.I,
)

RESEARCH_SIGNAL_RE = re.compile(
    r"(知识库|文档库|检索|联网|上网|知识图谱|本体图谱|"
    r"knowledge_retrieve|web_search|kg_query)",
    re.I,
)

COMPOUND_SEQUENTIAL_RE = re.compile(
    r"(?:先|首先).{0,24}(?:然后|接着|之后|再)|"
    r"(?:然后|接着|之后|再).{0,24}(?:创建|添加|移动|分享|提醒|待办|定时)",
    re.I,
)

COMPOUND_PARALLEL_RE = re.compile(
    r"(?:同时|一并|顺便|以及|还有|并且).{0,20}(?:查|检索|搜索|待办|定时|提醒|列表|文件夹)|"
    r"(?:查|检索|搜索).{0,24}(?:同时|顺便|以及|还有).{0,24}(?:待办|定时|提醒|列表|文件夹)",
    re.I,
)

TRIVIAL_DIRECT_RE = re.compile(
    r"^[\d\s\+\-\*/\(\)\.=]{2,}(?:等于|是)?\s*多少",
    re.I,
)

MERMAID_DIAGRAM_SKILL = "mermaid-diagram"


# ═══════════════════════════════════════════════════════════════
# 平台绑定信号函数
# ═══════════════════════════════════════════════════════════════


def is_skill_management_message(message: str) -> bool:
    """用户是否在创建/更新/删除 Skill。"""
    return bool(_SKILL_MANAGE_RE.search((message or "").strip()))


def is_diagram_generation_message(message: str) -> bool:
    """用户是否要生成思维导图、流程图等 Mermaid 图表。"""
    msg = (message or "").strip()
    if not msg or is_skill_management_message(msg):
        return False
    return bool(_DIAGRAM_INTENT_RE.search(msg))


def user_wants_browser_screenshot(message: str) -> bool:
    """用户是否明确要求浏览器截图。"""
    return bool(_SCREENSHOT_INTENT_RE.search((message or "").strip()))


def skill_creation_needs_site_research(message: str) -> bool:
    """编写抓取类 Skill 前是否必须先探查网页/数据源。"""
    msg = (message or "").strip()
    return bool(_URL_IN_MESSAGE_RE.search(msg) or _PAGE_INTENT_RE.search(msg))


def skill_creation_requires_python_script(message: str) -> bool:
    """除极简指令型外，发展技能应含可执行 Python 脚本。"""
    msg = (message or "").strip()
    if not is_skill_management_message(msg):
        return False
    if _SKILL_INSTRUCTION_ONLY_RE.search(msg):
        return False
    if skill_creation_needs_site_research(msg):
        return True
    return bool(_SCRIPT_TASK_RE.search(msg))


def should_read_memory(message: str) -> bool:
    """用户是否在询问之前记住的信息。"""
    return bool(_MEMORY_READ_RE.search((message or "").strip()))


def should_write_memory(message: str) -> bool:
    """用户是否在要求记住某信息。"""
    return bool(_MEMORY_WRITE_RE.search((message or "").strip()))


def is_inconclusive_skill_conclusion(text: str) -> bool:
    """脚本虽返回结论，但内容表明任务未成功完成。"""
    body = (text or "").strip()
    if not body or len(body) < 6:
        return True
    return bool(_INCONCLUSIVE_SKILL_CONCLUSION_RE.search(body))


# 平台使用问询匹配
_PLATFORM_USAGE_RE = re.compile(
    r"(怎么|如何|怎样|在哪|哪里|能不能).{0,16}(上传|分享|翻译|权限|知识库|导出|下载|登录|注册|设置|使用)"
    r"|平台.{0,8}(功能|使用|操作|入口)"
)

# 平台用户/部门/组织等系统数据查询（走平台操作 Agent，勿误路由检索专精）
_PLATFORM_SYS_DATA_RE = re.compile(
    r"(?:系统|平台|组织|部门|成员|账号).{0,12}(?:用户|人员|成员|部门|组织)"
    r"|(?:用户|人员|成员|部门|组织).{0,12}(?:列表|有哪些|多少|几个|查询|查看|管理|架构|树)"
    r"|list_users|list_departments|"
    r"有哪些用户|用户列表|部门列表|组织架构|组织树|"
    r"谁在平台|平台上有谁",
    re.I,
)

# 「咨询服务部有哪些人」类：指定部门/组织单元的成员清单
_ORG_MEMBER_LIST_RE = re.compile(
    r"(?:有哪些|有谁|多少|几个|列出|名单)(?:人|成员|员工|同事)?"
    r"|(?:成员|人员|员工|同事)(?:列表|清单|有谁)?"
    r"|谁(?:在|属于|是).{0,6}(?:部|组|中心|团队)",
    re.I,
)
_ORG_UNIT_MARK_RE = re.compile(r"(?:部|部门|组|中心|团队|科室|处|室)", re.I)


def is_org_member_list_question(message: str) -> bool:
    """询问某部门/组织单元有哪些成员（须走 platform + 图谱，禁止 LLM 编造名单）。"""
    msg = (message or "").strip()
    if not msg or not _ORG_MEMBER_LIST_RE.search(msg):
        return False
    return bool(_ORG_UNIT_MARK_RE.search(msg) or _PLATFORM_SYS_DATA_RE.search(msg))


def is_platform_system_data_message(message: str) -> bool:
    """用户是否在查询/管理平台用户、部门等系统数据。"""
    if is_org_member_list_question(message):
        return True
    return bool(_PLATFORM_SYS_DATA_RE.search((message or "").strip()))


def is_platform_usage_message(message: str) -> bool:
    return bool(_PLATFORM_USAGE_RE.search((message or "").strip()))


def is_platform_operation_message(message: str) -> bool:
    """系统操作类诉求：文档库/待办/通知/用户部门等（非知识库内容调研）。"""
    msg = (message or "").strip()
    if not msg:
        return False
    if is_platform_usage_message(msg) or is_platform_system_data_message(msg):
        return True
    return bool(
        re.search(
            r"(?:文档库|文件夹|我的文件|待办|todo|"
            r"list_document|list_library|list_manageable|list_todos|"
            r"list_users|list_departments|"
            r"用户管理|部门管理|系统设置|"
            r"send_notification|schedule_notification|"
            r"创建.{0,4}待办|分享.{0,4}文档|上传.{0,6}文档)",
            msg,
            re.I,
        )
    )


_WEB_SKILL_DESC_RE = re.compile(
    r"网页|抓取|爬取|拉取|http|url|洞察|页面|行情|价格|数据", re.I
)


def validate_uploaded_skill_load(
    *,
    user_message: str,
    skill_name: str,
    skill_description: str,
    skill_source: SkillSource,
    planned_skill: str | None = None,
    created_skills: tuple[str, ...] | None = None,
) -> tuple[bool, str]:
    """服务端校验 load_uploaded_skill 是否与用户意图匹配。"""
    name = (skill_name or "").strip()
    msg = (user_message or "").strip()
    if not name:
        return False, "缺少 skill_name"

    name_key = name.casefold()
    created_keys = {
        (s or "").strip().casefold() for s in (created_skills or ()) if (s or "").strip()
    }
    if name_key in created_keys:
        return True, ""

    planned = (planned_skill or "").strip()
    if planned and name_key == planned.casefold():
        return True, ""

    if skill_source != SkillSource.UPLOADED:
        return (
            False,
            f"`{name}` 是内置技能，请按其编排调用原子工具，勿使用 load_uploaded_skill",
        )

    if is_skill_management_message(msg) and name_key not in created_keys:
        planned_key = (planned or "").casefold()
        if not planned_key or name_key != planned_key:
            return (
                False,
                "创建/生成 Skill 请直接用 create_skill 生成新包，"
                "勿 list_agent_skills、勿 load/run 已有技能；"
                "创建后再 run_skill_script 验证",
            )

    if name.casefold() in msg.casefold():
        return True, ""

    desc = (skill_description or "").strip()
    if desc and _message_aligns_with_skill(msg, desc):
        return True, ""

    short_desc = desc[:72] + ("…" if len(desc) > 72 else "")
    return (
        False,
        f"用户请求与上传 Skill `{name}` 的用途不匹配（{short_desc}）。"
        "请根据 Skills 目录摘要查找可复用技能并 load/run；"
        "无匹配且用户需要新能力时再 create_skill，否则直接回答用户问题",
    )


_STOPWORDS = frozenset(
    {"skill", "skills", "markdown", "平台", "用户", "支持", "需要", "流程", "按照", "使用"}
)

_MATH_TASK_RE = re.compile(r"[\d]{2,}\s*[×xX*·]\s*[\d]{2,}|乘|乘法|乘以|竖式|计算")
_MATH_SKILL_RE = re.compile(r"乘|乘法|竖式|计算|multipl|digit|arithmetic", re.I)


def _desc_keywords(description: str) -> list[str]:
    """从描述中提取中文二元/三元片段与 slug 词，避免整句合并导致无法命中。"""
    desc = (description or "").casefold()
    out: list[str] = []
    out.extend(re.findall(r"[a-z][a-z0-9-]{2,}", desc))
    for run in re.findall(r"[\u4e00-\u9fff]+", desc):
        if len(run) >= 2:
            for i in range(len(run) - 1):
                out.append(run[i : i + 2])
        if len(run) >= 3:
            for i in range(len(run) - 2):
                out.append(run[i : i + 3])
    return out


def _message_aligns_with_skill(message: str, description: str) -> bool:
    """保守匹配：用户消息与 skill 描述中的关键场景词有交集。"""
    msg = message.casefold()
    desc = (description or "").casefold()
    if _WEB_SKILL_DESC_RE.search(desc):
        if (
            _URL_IN_MESSAGE_RE.search(message)
            or _DOMAIN_IN_MESSAGE_RE.search(message)
            or _PAGE_INTENT_RE.search(message)
        ):
            return True
    if _MATH_SKILL_RE.search(desc) and _MATH_TASK_RE.search(message):
        return True
    for token in _desc_keywords(desc):
        if token in _STOPWORDS or len(token) < 2:
            continue
        if token in msg and (len(token) >= 3 or any("\u4e00" <= c <= "\u9fff" for c in token)):
            return True
    return False


def append_skill_repair_context(loop_state: LoopState | None, skill_name: str, reason: str) -> None:
    from app.core.agent_tool_context import append_skill_repair_context as _append

    _append(loop_state, skill_name=skill_name, reason=reason)


def extract_memory_note(message: str, *, max_len: int = 500) -> str:
    """从用户消息提取待写入记忆的要点。"""
    text = (message or "").strip()
    for prefix in (
        "请记住",
        "帮我记住",
        "帮我记一下",
        "记下来",
        "以后记得",
        "别忘了",
    ):
        if text.startswith(prefix):
            text = text[len(prefix) :].lstrip("：:，, ")
            break
    text = text.strip("。.")
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    return text or (message or "").strip()[:max_len]


# ═══════════════════════════════════════════════════════════════
# 路由信号检测（原 agent_routing_signals.py）
# ═══════════════════════════════════════════════════════════════


def message_has_url(message: str) -> bool:
    return bool(_URL_IN_MESSAGE_RE.search((message or "").strip()))


def message_has_page_intent(message: str) -> bool:
    return bool(_PAGE_INTENT_RE.search((message or "").strip()))


def matches_platform_ops_extra(message: str) -> bool:
    return bool(PLATFORM_OPS_EXTRA_RE.search((message or "").strip()))


def matches_scheduler_intent(message: str) -> bool:
    return bool(SCHEDULER_RE.search((message or "").strip()))


def matches_search_rpa_research_intent(message: str) -> bool:
    """「搜索 rpa」类主题调研：RPA 为检索对象，非浏览器操作。"""
    msg = (message or "").strip()
    if not SEARCH_RPA_TOPIC_RE.search(msg):
        return False
    return not SEARCH_RPA_BROWSER_ACTION_RE.search(msg)


def matches_search_rpa_browser_intent(message: str) -> bool:
    """「搜索 rpa 并截图」类：需在浏览器中操作并取证。"""
    msg = (message or "").strip()
    if not SEARCH_RPA_TOPIC_RE.search(msg):
        return False
    return bool(SEARCH_RPA_BROWSER_ACTION_RE.search(msg))


def matches_browser_intent(message: str) -> bool:
    msg = (message or "").strip()
    if matches_search_rpa_research_intent(msg):
        return False
    return bool(
        BROWSER_RE.search(msg)
        or message_has_url(msg)
        or message_has_page_intent(msg)
        or matches_search_rpa_browser_intent(msg)
    )


def matches_browser_site_search(message: str) -> bool:
    return bool(BROWSER_SITE_SEARCH_RE.search((message or "").strip()))


def matches_research_signal(message: str) -> bool:
    return bool(RESEARCH_SIGNAL_RE.search((message or "").strip()))


def is_compound_sequential_message(message: str) -> bool:
    return bool(COMPOUND_SEQUENTIAL_RE.search((message or "").strip()))


def is_compound_parallel_message(message: str) -> bool:
    return bool(COMPOUND_PARALLEL_RE.search((message or "").strip()))


def is_trivial_direct_question(message: str) -> bool:
    text = (message or "").strip()
    if not text or len(text) > 48:
        return False
    if matches_research_signal(text) or matches_platform_ops_extra(text):
        return False
    if is_platform_operation_message(text):
        return False
    return bool(TRIVIAL_DIRECT_RE.match(text))
