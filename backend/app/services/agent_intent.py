"""AI 智能体意图判断 — 从用户消息推断是否需要检索、联网或仅寒暄。"""

from __future__ import annotations

import re

from app.agentkit.loop import AgentToolPlan

from app.schemas.ai_chat import AiChatMessage
from app.services.agent_skill_router import is_platform_usage_message, is_platform_operation_message, is_platform_system_data_message
from app.core.conversation_turn_context import is_likely_follow_up

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
    r"(?:随便)?聊聊|闲聊一下|闲聊|讲个笑话|"
    r"我是\S+|我叫\S+"
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
    r"|(?:介绍).{0,8}(?:文档|报告|方法|背景|概况|技术|流程)"
)

# 仅用户明确要求联网/外部检索时触发（不用领域词表推断）
_EXPLICIT_RETRIEVAL_ACTION_RE = re.compile(
    r"(?:检索|搜索|查资料|查一下|查询|联网|上网|知识库|文档库|本体图谱|知识图谱|"
    r"web_search|knowledge_retrieve|kg_query|写报告|生成报告|撰写报告)",
    re.I,
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

_SIMPLE_DEFINE_RE = re.compile(r"^什么是.{1,16}[？?]?$", re.I)

_EXPLICIT_WEB_RE = re.compile(
    r"(?:联网|上网|网上(?:查|搜|搜索)|搜索(?:一下|互联网)|"
    r"查(?:一下|下)?(?:网|网上|互联网)|"
    r"互联网(?:上)?(?:查|搜|检索)|在线(?:查|搜|搜索|检索))"
)


def has_explicit_specialist_intent(
    message: str,
    *,
    history: list[AiChatMessage] | None = None,
) -> bool:
    """用户是否明确要求专精 Agent（平台/浏览器/Skill 等）。

    Orchestrator 可直接回复的仅有寒暄/极简问答/简单定义。
    图表绘制、定时提醒、联网检索等需要执行的任务由路由分配专精 Agent。"""
    from app.services.agent_skill_router import (
        is_platform_operation_message,
        is_platform_system_data_message,
        is_skill_management_message,
        matches_browser_intent,
        matches_platform_ops_extra,
    )
    text = (message or "").strip()
    if not text:
        return False
    if is_skill_management_message(text):
        return True
    # 以下均为专精 Agent 的领域，路由分配
    if is_platform_operation_message(text) or is_platform_system_data_message(text):
        return True
    if matches_platform_ops_extra(text):
        return True
    if matches_browser_intent(text):
        return True
    if _EXPLICIT_KB_RE.search(text) or _EXPLICIT_KG_RE.search(text):
        return True
    if _EXPLICIT_WEB_RE.search(text) or _EXPLICIT_RETRIEVAL_ACTION_RE.search(text):
        return True
    if history and is_likely_follow_up(text, history) and _history_had_retrieval_question(history):
        return True
    return False


# 短消息中明确需要工具的动词 — Orchestrator 不直接处理，交由路由分配子智能体
_ACTION_VERB_RE = re.compile(
    r"(提醒|通知|定时|发送|分享|上传|下载|删除|创建|生成|写[一啊]?个|"
    r"查[一一下]|搜索|检索|翻译|计算|转换|换算|设定|设置|配置|"
    r"打开|关闭|启动|停止|爬取|抓取|同步|监控|"
    r"使用|执行|运行|加载)",
    re.I,
)


def should_orchestrator_reply_directly(
    message: str,
    history: list[AiChatMessage] | None = None,
) -> bool:
    """Orchestrator 是否可以直接回复（不进入任何工具循环或子智能体）。

    设计原则：Orchestrator 仅能直接回复的场景：
    - 纯寒暄（Step 1）
    - 极简常识/计算题（Step 2）
    - 短消息兜底（Step 6）

    其他任何需要执行的任务（联网搜索、知识库检索、图谱查询、图表绘制、
    定时/通知、平台操作、浏览器自动化等）全部路由到专精 Agent 或子智能体完成。
    """
    from app.services.agent_skill_router import (
        is_trivial_direct_question,
    )

    text = (message or "").strip()
    if not text:
        return True

    # ── Step 1: 寒暄检查 ──
    if is_chitchat_message(text, history):
        return True

    # ── Step 2: 极简计算题 ──
    if is_trivial_direct_question(text):
        return True

    # ── Step 3: 专精意图检查（路由分配） ──
    if has_explicit_specialist_intent(text, history=history):
        return False

    # ── Step 4: 追问检查 ──
    if is_likely_follow_up(text, history):
        return False

    # ── Step 5: 动词检测 ──
    if _ACTION_VERB_RE.search(text):
        return False

    # ── Step 7: 短消息兜底 ──
    if len(text) <= 14 and not _RETRIEVAL_HINT_RE.search(text):
        return True

    return False


def _is_compound_chitchat(text: str) -> bool:
    parts = [p.strip() for p in re.split(r"[，,。.!！?？\s]+", text) if p.strip()]
    if not parts or len(parts) > 4:
        return False
    return all(
        _CHITCHAT_FRAGMENT_RE.match(part) or _CHITCHAT_ONLY_RE.match(part)
        for part in parts
    )


def is_chitchat_message(
    text: str,
    history: list[AiChatMessage] | None = None,
) -> bool:
    """日常寒暄或闲聊，通常无需检索与读附件。"""
    t = (text or "").strip()
    if not t:
        return True
    if _EXPLICIT_KB_RE.search(t) or _EXPLICIT_KG_RE.search(t):
        return False
    # 寒暄优先于「有上文即追问」启发式，避免「你好」等被误路由到业务 Skill
    if _CHITCHAT_ONLY_RE.match(t) or _is_compound_chitchat(t):
        return True
    if len(t) <= 12 and _SHORT_CASUAL_RE.match(t):
        return True
    if history and is_likely_follow_up(t, history):
        return False
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
        return bool(
            _EXPLICIT_KB_RE.search(text)
            or _EXPLICIT_KG_RE.search(text)
            or _EXPLICIT_WEB_RE.search(text)
            or _EXPLICIT_RETRIEVAL_ACTION_RE.search(text)
        )
    return False


def needs_knowledge_retrieval(
    message: str,
    history: list[AiChatMessage] | None = None,
) -> bool:
    """问题是否明确要求查资料 / 知识库 / 联网（不用领域词推断）。"""
    text = (message or "").strip()
    from app.services.agent_skill_router import is_org_member_list_question

    if is_org_member_list_question(text):
        return False
    if is_platform_system_data_message(text) or is_platform_operation_message(text):
        return False
    if _EXPLICIT_KB_RE.search(text) or _EXPLICIT_KG_RE.search(text):
        return True
    if _EXPLICIT_WEB_RE.search(text) or _EXPLICIT_RETRIEVAL_ACTION_RE.search(text):
        return True
    if is_likely_follow_up(text, history):
        return _history_had_retrieval_question(history)
    return False


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
    if chitchat if chitchat is not None else is_chitchat_message(text, history):
        return True
    if platform_usage if platform_usage is not None else is_platform_usage_message(text):
        return True
    if should_orchestrator_reply_directly(text, history):
        return True
    return False


def needs_web_search(
    message: str,
    history: list[AiChatMessage] | None = None,
) -> bool:
    """SearXNG 可用时默认倾向联网，寒暄与平台操作类问题除外。"""
    return not _should_skip_web_search(message, history)



def plan_agent_tools(
    message: str,
    *,
    attach_count: int,
    history: list[AiChatMessage] | None = None,
) -> AgentToolPlan:
    """系统层 Hook：仅决定是否预读附件；检索/联网由智能体在 tool loop 内自行选用。"""
    text = (message or "").strip()
    explicit_kg = bool(_EXPLICIT_KG_RE.search(text))
    chitchat = is_chitchat_message(text, history)

    def _finish(
        *,
        use_attachment: bool,
        intent_label: str = "处理用户请求",
        context_instruction: str = "",
    ) -> AgentToolPlan:
        return AgentToolPlan(
            use_attachment=use_attachment,
            intent_label=intent_label,
            context_instruction=context_instruction,
        )

    if attach_count > 0 and not chitchat and not explicit_kg:
        return _finish(
            use_attachment=True,
            intent_label="依据用户上传的附件回答",
            context_instruction=_ATTACHMENT_CONTEXT_INSTRUCTION,
        )
    return _finish(use_attachment=False)
