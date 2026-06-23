"""AI 智能体意图判断 — 从用户消息推断是否需要检索、联网或仅寒暄。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.schemas.ai_chat import AiChatMessage
from app.services.agent_skill_router import is_platform_usage_message

_ATTACHMENT_CONTEXT_INSTRUCTION = """以下是用户上传的临时附件正文（未写入知识库），请优先且主要依据附件内容回答。
若附件不足以回答，请明确说明缺口，不要编造附件中不存在的内容，也不要引用未提供的知识库片段。"""

_EXPLICIT_KB_RE = re.compile(
    r"(知识库|文档库|我的文档|权限内.{0,6}(文档|资料)|"
    r"检索.{0,8}(文档|资料|知识库)|"
    r"(和|与|跟|对比|比较).{0,8}知识库|"
    r"知识库.{0,8}(里|中|内)|"
    r"库里.{0,8}(文档|资料|有没有))"
)

_EXPLICIT_KG_RE = re.compile(r"(本体图谱|知识图谱|图谱里|图谱中|实体关系)")

_CHITCHAT_ONLY_RE = re.compile(
    r"^(?:"
    r"你好|您好|hi|hello|hey|嗨|早上好|下午好|晚上好|"
    r"你是谁|你是哪位|你叫什么|你是谁啊|你谁啊|你是？|"
    r"你是什么|你是什么模型|你是啥|你是哪个模型|你是哪个助手|"
    r"介绍一下自己|介绍你自己|自我介绍|"
    r"谢谢|感谢|多谢|辛苦了|"
    r"再见|拜拜|bye|"
    r"好的|好哒|明白|知道了|收到|没问题|ok|okay|"
    r"在吗|在不在|"
    r"你能做什么|你会什么|你能帮我什么|有什么功能|"
    r"(?:随便)?聊聊|闲聊一下|闲聊|讲个笑话"
    r")(?:[!！?？呀啊吧呢嘛。.,，~～\s]*)$",
    re.I,
)

_CHITCHAT_FRAGMENT_RE = re.compile(
    r"^(?:"
    r"你好|您好|嗨|谢谢|感谢|多谢|再见|拜拜|在吗|在不在|"
    r"你是谁|你是哪位|你叫什么|你是什么|辛苦了|好的|明白|知道了|收到|没问题"
    r")(?:[!！?？呀啊吧呢嘛。.,，~～\s]*)$",
    re.I,
)

_RETRIEVAL_HINT_RE = re.compile(
    r"(?:什么|为何|为什么|哪些|哪个|多少|是否|有没有)"
    r"|(?:怎么|如何|怎样|能不能|可不可以)"
    r"|(?:查|检索|搜索|找|分析|总结|对比|比较|解释|说明|撰写|写|翻译)"
    r"|(?:介绍).{0,8}(?:政策|文档|报告|方法|背景|概况|技术|流程)"
    r"|(?:碳|政策|排放|配额|法规|标准|文档|报告|论文|数据|市场|行业|企业|知识库|图谱|实体)"
)

_SHORT_CASUAL_RE = re.compile(
    r"^(?:嗯|哦|啊|哈|好|行|可以|不错|厉害|哈哈|嘻嘻|嘿嘿|加油|"
    r"辛苦了|没事了|算了|好吧|就这样)(?:[!！?？。.,，~～\s]*)$",
    re.I,
)

_FOLLOWUP_RE = re.compile(
    r"(?:继续|然后|还有|进一步|详细|展开|具体|再说说|刚才|上面|前述|前面说的|"
    r"第二点|第三点|上一条|补充一下)"
)

_EXPLICIT_WEB_RE = re.compile(
    r"(?:联网|上网|网上(?:查|搜|搜索)|搜索(?:一下|互联网)|"
    r"查(?:一下|下)?(?:网|网上|互联网)|"
    r"互联网(?:上)?(?:查|搜|检索)|在线(?:查|搜|搜索|检索))"
)

_REMINDER_ACTION_RE = re.compile(
    r"(?:提醒|通知|叫我|告诉我|记得提醒|记得通知)",
    re.I,
)

_REMINDER_DELAY_RE = re.compile(
    r"(\d+)\s*(秒(?:钟)?|分钟?|分|小时?|时|个小时)(?:之)?后",
    re.I,
)


def _is_compound_chitchat(text: str) -> bool:
    parts = [p.strip() for p in re.split(r"[，,。.!！?？\s]+", text) if p.strip()]
    if not parts or len(parts) > 4:
        return False
    return all(
        _CHITCHAT_FRAGMENT_RE.match(part) or _CHITCHAT_ONLY_RE.match(part)
        for part in parts
    )


def is_chitchat_message(text: str) -> bool:
    """日常寒暄或闲聊，通常无需检索与读附件。"""
    t = (text or "").strip()
    if not t:
        return True
    if is_scheduled_reminder_request(t):
        return False
    if _EXPLICIT_KB_RE.search(t) or _EXPLICIT_KG_RE.search(t):
        return False
    if _CHITCHAT_ONLY_RE.match(t) or _is_compound_chitchat(t):
        return True
    if len(t) <= 12 and _SHORT_CASUAL_RE.match(t):
        return True
    if _RETRIEVAL_HINT_RE.search(t):
        return False
    return False


def _history_had_retrieval_question(history: list[AiChatMessage] | None) -> bool:
    if not history:
        return False
    for item in reversed(history):
        if item.role != "user":
            continue
        text = (item.content or "").strip()
        return bool(_RETRIEVAL_HINT_RE.search(text) or _EXPLICIT_KB_RE.search(text))
    return False


def is_scheduled_reminder_request(text: str) -> bool:
    """用户是否在请求「N 秒后/分钟后提醒」。"""
    return parse_scheduled_reminder_request(text) is not None


def _extract_reminder_title(text: str) -> str:
    remainder = _REMINDER_DELAY_RE.sub("", text, count=1).strip()
    for prefix in ("提醒我", "通知我", "叫我", "告诉我", "记得提醒", "记得通知", "提醒", "通知"):
        if remainder.startswith(prefix):
            remainder = remainder[len(prefix) :].strip()
            break
    remainder = re.sub(r"[吧呢啊。！!？?，,\s]+$", "", remainder)
    return (remainder or "提醒")[:80]


def parse_scheduled_reminder_request(text: str) -> dict[str, Any] | None:
    """解析明确的定时提醒请求，供服务端直接 schedule_notification。"""
    raw = (text or "").strip()
    if not raw:
        return None
    delay_match = _REMINDER_DELAY_RE.search(raw)
    if not delay_match:
        return None
    if not _REMINDER_ACTION_RE.search(raw) and "后" not in raw:
        return None

    amount = int(delay_match.group(1))
    if amount <= 0:
        return None

    unit = delay_match.group(2).lower()
    delay_seconds: int | None = None
    delay_minutes: int | None = None
    if unit.startswith("秒"):
        delay_seconds = amount
    elif unit in ("分", "分钟"):
        delay_minutes = amount
    elif unit.startswith("时") or unit == "个小时":
        delay_minutes = amount * 60
    else:
        return None

    title = _extract_reminder_title(raw)
    return {
        "title": title,
        "body": "",
        "delay_seconds": delay_seconds,
        "delay_minutes": delay_minutes,
    }


def needs_knowledge_retrieval(
    message: str,
    history: list[AiChatMessage] | None = None,
) -> bool:
    """问题是否像「查资料 / 问制度 / 问文档内容」。"""
    text = (message or "").strip()
    if _RETRIEVAL_HINT_RE.search(text):
        return True
    if _EXPLICIT_KB_RE.search(text) or _EXPLICIT_KG_RE.search(text):
        return True
    return bool(_FOLLOWUP_RE.search(text) and _history_had_retrieval_question(history))


def _should_skip_web_search(
    message: str,
    history: list[AiChatMessage] | None = None,
    *,
    chitchat: bool | None = None,
    platform_usage: bool | None = None,
) -> bool:
    text = (message or "").strip()
    if not text or _EXPLICIT_WEB_RE.search(text):
        return not bool(text)
    if chitchat if chitchat is not None else is_chitchat_message(text):
        return True
    if platform_usage if platform_usage is not None else is_platform_usage_message(text):
        return True
    if (
        len(text) <= 20
        and not _RETRIEVAL_HINT_RE.search(text)
        and not needs_knowledge_retrieval(text, history)
        and not _FOLLOWUP_RE.search(text)
    ):
        return True
    return False


def needs_web_search(
    message: str,
    history: list[AiChatMessage] | None = None,
) -> bool:
    """SearXNG 可用时默认倾向联网，寒暄与平台操作类问题除外。"""
    return not _should_skip_web_search(message, history)


@dataclass(frozen=True)
class AgentToolPlan:
    use_attachment: bool
    use_doc_retrieval: bool
    use_kg: bool
    use_web_search: bool
    intent_label: str
    context_instruction: str


def plan_agent_tools(
    message: str,
    *,
    attach_count: int,
    kb_enabled: bool,
    kg_enabled: bool,
    web_enabled: bool,
    history: list[AiChatMessage] | None = None,
) -> AgentToolPlan:
    """系统层 Hook：仅决定是否预读附件；检索由 tool loop 按需执行。"""
    text = (message or "").strip()
    explicit_kb = bool(_EXPLICIT_KB_RE.search(text))
    explicit_kg = bool(_EXPLICIT_KG_RE.search(text))
    platform_usage = is_platform_usage_message(text)
    chitchat = is_chitchat_message(text)

    def _finish(
        *,
        use_attachment: bool,
        intent_label: str,
        context_instruction: str = "",
    ) -> AgentToolPlan:
        return AgentToolPlan(
            use_attachment=use_attachment,
            use_doc_retrieval=False,
            use_kg=False,
            use_web_search=False,
            intent_label=intent_label,
            context_instruction=context_instruction,
        )

    if chitchat and not explicit_kb and not explicit_kg:
        return _finish(use_attachment=False, intent_label="日常交流，直接回答")
    if is_scheduled_reminder_request(text) and not explicit_kb and not explicit_kg:
        return _finish(use_attachment=False, intent_label="设置定时提醒")
    if platform_usage and not explicit_kb and not explicit_kg:
        return _finish(use_attachment=False, intent_label="解答平台使用问题")
    if attach_count > 0 and not chitchat:
        return _finish(
            use_attachment=True,
            intent_label="依据用户上传的附件回答",
            context_instruction=_ATTACHMENT_CONTEXT_INSTRUCTION,
        )
    return _finish(use_attachment=False, intent_label="由智能体按需调用工具")
