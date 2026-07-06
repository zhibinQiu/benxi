"""Agent 路由与意图共享信号（纯 regex / 函数，无 DB）。"""

from __future__ import annotations

import re

from app.services.agent_skill_router import (
    _PAGE_INTENT_RE,
    _URL_IN_MESSAGE_RE,
    is_platform_operation_message,
)

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
