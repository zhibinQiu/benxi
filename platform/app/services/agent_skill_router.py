"""上传型 Skill 路由 — 记忆、平台用法与 Skill 加载校验。"""

from __future__ import annotations

import re
from typing import Any

from app.skills.types import SkillSource

_MEMORY_READ_RE = re.compile(
    r"(?:上次|之前|还记得|记住的|以前.{0,4}聊|延续.{0,4}会话|我的偏好)"
)

_MEMORY_WRITE_RE = re.compile(
    r"(?:请记住|帮我记|记下来|以后记得|别忘了)"
)

_PLATFORM_USAGE_RE = re.compile(
    r"(怎么|如何|怎样|在哪|哪里|能不能).{0,16}(上传|分享|翻译|权限|知识库|导出|下载|登录|注册|设置|使用)"
    r"|平台.{0,8}(功能|使用|操作|入口)"
)

_SKILL_MANAGE_RE = re.compile(
    r"(?:创建|新建|编写|写一个|做一个|生成|更新|修改|删除).{0,16}(?:skill|技能|Skills?)"
    r"|(?:skill|技能|Skills?).{0,10}(?:创建|新建|编写|更新|修改|删除)"
    r"|帮我.{0,8}(?:skill|技能)"
)

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
_SKILL_INSTRUCTION_ONLY_RE = re.compile(
    r"仅说明|纯指令|不要脚本|不写脚本|无需脚本|instruction.only|"
    r"mermaid|流程图说明|只写.{0,4}说明",
    re.I,
)
_SCRIPT_TASK_RE = re.compile(
    r"爬取|抓取|拉取|脚本|执行|运行|数据|api|自动化|价格|行情|采集|同步|监控",
    re.I,
)


def should_read_memory(message: str) -> bool:
    return bool(_MEMORY_READ_RE.search((message or "").strip()))


def should_write_memory(message: str) -> bool:
    return bool(_MEMORY_WRITE_RE.search((message or "").strip()))


def is_platform_usage_message(message: str) -> bool:
    return bool(_PLATFORM_USAGE_RE.search((message or "").strip()))


def is_skill_management_message(message: str) -> bool:
    """用户是否在创建/更新/删除 Skill，而非使用已有 Skill 执行任务。"""
    return bool(_SKILL_MANAGE_RE.search((message or "").strip()))


def user_wants_browser_screenshot(message: str) -> bool:
    """用户是否明确要求浏览器截图（与 Skill 编写探页不同）。"""
    return bool(_SCREENSHOT_INTENT_RE.search((message or "").strip()))


def skill_creation_needs_site_research(message: str) -> bool:
    """编写抓取类 Skill 前是否必须先探查网页/数据源。"""
    msg = (message or "").strip()
    return bool(_URL_IN_MESSAGE_RE.search(msg) or _PAGE_INTENT_RE.search(msg))


def skill_creation_requires_python_script(message: str) -> bool:
    """除极简指令型外，发展技能应含可执行 Python 脚本（main.py）。"""
    msg = (message or "").strip()
    if not is_skill_management_message(msg):
        return False
    if _SKILL_INSTRUCTION_ONLY_RE.search(msg):
        return False
    if skill_creation_needs_site_research(msg):
        return True
    return bool(_SCRIPT_TASK_RE.search(msg))


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

    if is_skill_management_message(msg) and name.casefold() not in msg.casefold():
        return (
            False,
            "当前为 Skill 管理请求（创建/更新/删除），请使用 create_uploaded_skill 等工具，"
            f"勿加载无关的上传 Skill `{name}`",
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
        "请根据 Skills 目录摘要判断是否加载；无关时直接回答或使用 create_uploaded_skill",
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


_INCONCLUSIVE_SKILL_CONCLUSION_RE = re.compile(
    r"无法|失败|未能|不知道|没有结果|无结论|无有效|未获取|未找到|"
    r"请检查|不能完成|超时|timeout|error|exception|traceback",
    re.I,
)


def is_inconclusive_skill_conclusion(text: str) -> bool:
    """脚本虽返回 conclusion，但内容表明任务未成功完成。"""
    body = (text or "").strip()
    if not body:
        return True
    if len(body) < 6:
        return True
    return bool(_INCONCLUSIVE_SKILL_CONCLUSION_RE.search(body))


def append_skill_repair_context(loop_state: dict[str, Any] | None, skill_name: str, reason: str) -> None:
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
