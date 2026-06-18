"""AI 首页 — AI 智能体对话（内置 DeepSeek LLM）。"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.exceptions import bad_request
from app.core.permissions import user_has_permission
from app.core.platform_assistant import assistant_ai_home_persona
from app.integrations.deepseek_client import is_configured, resolve_credentials
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services import platform_chat_store
from app.services.kg_service import KgQaContext, merge_kg_qa_into_context, retrieve_kg_context_for_question

_MAX_HISTORY = 20
_MAX_QUERYABLE_DOCS = 20

_SYSTEM_PROMPT = f"""{assistant_ai_home_persona()}。

你的能力包括：
- 以「小析」身份解答文档管理、权限分享、PDF 翻译、知识检索等平台使用问题
- 结合权限内文档检索片段与本体图谱实体关系，回答业务相关问题
- 对实时行情、最新价格、近期动态等时效性问题，结合互联网检索摘要作答
- 协助梳理办公场景下的信息整理、写作润色与数据分析思路

回答要求：
- 使用简体中文，结构清晰，可使用简短 Markdown
- 自我介绍或提及助手时统一使用名称「小析」
- 对不确定的政策或数据应说明需以官方来源为准，勿编造具体数值或文号
- 引用文档片段、图谱事实或联网摘要时在句末标注编号，格式为 [1]、[2]
- 超出平台或办公场景的问题可简要回应并引导回相关能力"""

_RETRIEVAL_CONTEXT_INSTRUCTION = """以下是从用户权限内文档检索到的相关片段，以及（若有）从本体图谱解析出的实体与关系上下文。
请在回答中优先参考这些材料；引用时在句末标注编号 [1]、[2]。若材料未覆盖问题，可结合专业知识补充并说明缺口。"""

_ATTACHMENT_CONTEXT_INSTRUCTION = """以下是用户上传的临时附件正文（未写入知识库），请优先且主要依据附件内容回答。
若附件不足以回答，请明确说明缺口，不要编造附件中不存在的内容，也不要引用未提供的知识库片段。"""

_MIXED_ATTACHMENT_KB_INSTRUCTION = """以下包含用户上传的临时附件，以及（若有）从权限内知识库检索到的片段或本体图谱上下文。
请按问题意图选用材料：分析「这篇/该文/附件」时以附件为主；明确要求对比或检索知识库时结合检索片段；引用检索片段时用 [1]、[2]。"""

_WEB_SEARCH_CONTEXT_INSTRUCTION = """以下是从互联网检索到的相关摘要（实时性信息以检索结果为准，并说明数据日期或来源局限）。
请在回答中优先参考这些材料；引用时在句末标注编号 [1]、[2]。若检索结果不足以给出准确数值，请明确说明并建议查阅官方平台的最新公告。"""

_MIXED_RETRIEVAL_WEB_INSTRUCTION = """以下包含权限内文档/本体图谱检索结果，以及（若有）互联网检索摘要。
实时行情、价格类问题优先参考联网材料；政策解读与流程说明优先参考文档/图谱材料；引用时在句末标注 [1]、[2]。"""

_EXPLICIT_KB_RE = re.compile(
    r"(知识库|文档库|我的文档|权限内.{0,6}(文档|资料)|"
    r"检索.{0,8}(文档|资料|知识库)|"
    r"(和|与|跟|对比|比较).{0,8}知识库|"
    r"知识库.{0,8}(里|中|内)|"
    r"库里.{0,8}(文档|资料|有没有))"
)

_EXPLICIT_KG_RE = re.compile(r"(本体图谱|知识图谱|图谱里|图谱中|实体关系)")

_PLATFORM_USAGE_RE = re.compile(
    r"(怎么|如何|怎样|在哪|哪里|能不能).{0,16}(上传|分享|翻译|权限|知识库|导出|下载|登录|注册|设置|使用)"
    r"|平台.{0,8}(功能|使用|操作|入口)"
)

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
    r"(?:联网|上网|网上(?:查|搜|搜索)|搜索(?:一下|互联网)|查一下(?:网|网上)|"
    r"互联网(?:上)?(?:查|搜|检索))"
)

_REALTIME_RE = re.compile(
    r"(?:最近|最新|当前|现在|今天|今日|实时|近期|本周|本月|今年|刚才|此刻|目前市场上|目前)"
)

_DATA_QUERY_RE = re.compile(
    r"(?:价格|行情|报价|收盘价|开盘价|汇率|股价|碳价|配额价|成交价|涨跌|涨幅|市值|指数|"
    r"CEA|CCER|排放权)"
)

_DATA_AMOUNT_RE = re.compile(r"(?:多少|是多少|什么价|几点|多高|多低|多少钱)")

_NEWS_REALTIME_RE = re.compile(
    r"(?:最近|最新|今天|今日|近期).{0,12}(?:新闻|动态|进展|公告|政策|规定|通知)"
)

_MAX_WEB_ITEMS = 8


def _is_compound_chitchat(text: str) -> bool:
    """复合寒暄，如「你好，你是谁？」。"""
    parts = [p.strip() for p in re.split(r"[，,。.!！?？\s]+", text) if p.strip()]
    if not parts or len(parts) > 4:
        return False
    return all(
        _CHITCHAT_FRAGMENT_RE.match(part) or _CHITCHAT_ONLY_RE.match(part)
        for part in parts
    )


def _is_chitchat_message(text: str) -> bool:
    """判断是否为无需检索、无需读取附件的日常寒暄或闲聊。"""
    t = (text or "").strip()
    if not t:
        return True
    if _EXPLICIT_KB_RE.search(t) or _EXPLICIT_KG_RE.search(t):
        return False
    if _CHITCHAT_ONLY_RE.match(t):
        return True
    if _is_compound_chitchat(t):
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
        if _RETRIEVAL_HINT_RE.search(text) or _EXPLICIT_KB_RE.search(text):
            return True
        return False
    return False


def _needs_knowledge_retrieval(
    message: str,
    history: list[AiChatMessage] | None = None,
) -> bool:
    text = (message or "").strip()
    if _RETRIEVAL_HINT_RE.search(text):
        return True
    if _EXPLICIT_KB_RE.search(text) or _EXPLICIT_KG_RE.search(text):
        return True
    if _FOLLOWUP_RE.search(text) and _history_had_retrieval_question(history):
        return True
    return False


def _history_had_web_question(history: list[AiChatMessage] | None) -> bool:
    if not history:
        return False
    for item in reversed(history):
        if item.role != "user":
            continue
        text = (item.content or "").strip()
        if _needs_web_search(text):
            return True
        return False
    return False


def _needs_web_search(
    message: str,
    history: list[AiChatMessage] | None = None,
) -> bool:
    """判断是否需要联网检索（实时行情、最新动态或用户明确要求）。"""
    text = (message or "").strip()
    if not text:
        return False
    if _EXPLICIT_WEB_RE.search(text):
        return True
    if _REALTIME_RE.search(text) and (
        _DATA_QUERY_RE.search(text) or _NEWS_REALTIME_RE.search(text)
    ):
        return True
    if _DATA_QUERY_RE.search(text) and _DATA_AMOUNT_RE.search(text):
        return True
    if _FOLLOWUP_RE.search(text) and _history_had_web_question(history):
        return True
    return False


def _web_search_fallback_after_empty_kb(message: str) -> bool:
    """本地文档未命中时，对数据/时效类问题尝试联网补充。"""
    text = (message or "").strip()
    if not text:
        return False
    return bool(
        _DATA_QUERY_RE.search(text)
        or _REALTIME_RE.search(text)
        or _NEWS_REALTIME_RE.search(text)
        or _EXPLICIT_WEB_RE.search(text)
    )


@dataclass(frozen=True)
class AgentToolPlan:
    use_attachment: bool
    use_doc_retrieval: bool
    use_kg: bool
    use_web_search: bool
    intent_label: str
    context_instruction: str


def _plan_agent_tools(
    message: str,
    *,
    attach_count: int,
    kb_enabled: bool,
    kg_enabled: bool,
    web_enabled: bool,
    history: list[AiChatMessage] | None = None,
) -> AgentToolPlan:
    """根据当前问题、对话历史与是否有附件，决定调用哪些工具。"""
    text = (message or "").strip()
    explicit_kb = bool(_EXPLICIT_KB_RE.search(text))
    explicit_kg = bool(_EXPLICIT_KG_RE.search(text))
    platform_usage = bool(_PLATFORM_USAGE_RE.search(text))
    chitchat = _is_chitchat_message(text)
    use_web = bool(web_enabled and _needs_web_search(text, history))

    if chitchat and not explicit_kb and not explicit_kg and not use_web:
        return AgentToolPlan(
            use_attachment=False,
            use_doc_retrieval=False,
            use_kg=False,
            use_web_search=False,
            intent_label="日常交流，直接回答",
            context_instruction="",
        )

    if platform_usage and not explicit_kb and not explicit_kg and not use_web:
        return AgentToolPlan(
            use_attachment=False,
            use_doc_retrieval=False,
            use_kg=False,
            use_web_search=False,
            intent_label="解答平台使用问题",
            context_instruction="",
        )

    # 有附件时默认读附件，但闲聊/平台问题已在上方提前返回，不会加载附件
    if attach_count > 0 and not chitchat:
        if explicit_kb:
            return AgentToolPlan(
                use_attachment=True,
                use_doc_retrieval=kb_enabled,
                use_kg=kg_enabled and explicit_kg,
                use_web_search=use_web,
                intent_label="结合附件与知识库回答",
                context_instruction=_MIXED_ATTACHMENT_KB_INSTRUCTION,
            )
        if explicit_kg:
            return AgentToolPlan(
                use_attachment=True,
                use_doc_retrieval=False,
                use_kg=kg_enabled,
                use_web_search=use_web,
                intent_label="结合附件与本体图谱回答",
                context_instruction=_MIXED_ATTACHMENT_KB_INSTRUCTION,
            )
        return AgentToolPlan(
            use_attachment=True,
            use_doc_retrieval=False,
            use_kg=False,
            use_web_search=use_web,
            intent_label="依据用户上传的附件回答",
            context_instruction=_ATTACHMENT_CONTEXT_INSTRUCTION,
        )

    needs_kb = _needs_knowledge_retrieval(text, history)
    if needs_kb or use_web:
        use_doc = bool(needs_kb and kb_enabled)
        use_kg = bool(needs_kb and kg_enabled)
        if use_web and use_doc:
            label = "检索文档并结合联网查询"
            instruction = _MIXED_RETRIEVAL_WEB_INSTRUCTION
        elif use_web:
            label = "联网检索实时信息"
            instruction = _WEB_SEARCH_CONTEXT_INSTRUCTION
        else:
            label = "检索权限内文档与本体图谱"
            instruction = _RETRIEVAL_CONTEXT_INSTRUCTION
        return AgentToolPlan(
            use_attachment=False,
            use_doc_retrieval=use_doc,
            use_kg=use_kg,
            use_web_search=use_web,
            intent_label=label,
            context_instruction=instruction,
        )

    return AgentToolPlan(
        use_attachment=False,
        use_doc_retrieval=False,
        use_kg=False,
        use_web_search=False,
        intent_label="直接回答",
        context_instruction="",
    )


def _kg_enabled_for_user(db: Session, user: User) -> bool:
    return user_has_permission(db, user, "feature.kg_palantir")


def _knowledge_search_enabled(db: Session, user: User) -> bool:
    return user_has_permission(db, user, "feature.knowledge_search")


def _web_search_enabled(db: Session | None) -> bool:
    from app.services.searxng_service import is_enabled

    return is_enabled(db)


def _resolve_web_search(
    db: Session | None,
    message: str,
    *,
    citation_start: int = 1,
) -> tuple[str, list[dict]]:
    if db is None:
        return "", []
    from app.services.report_generation_service import (
        _format_web_context,
        build_web_citations,
    )
    from app.services.searxng_service import (
        SearxngNotConfiguredError,
        SearxngSearchError,
        search_web,
    )

    q = (message or "").strip()[:120]
    if not q:
        return "", []
    try:
        items, _ = search_web(q, page_size=_MAX_WEB_ITEMS, db=db)
    except (SearxngNotConfiguredError, SearxngSearchError):
        return "", []
    except Exception:
        return "", []
    if not items:
        return "", []
    web_context = _format_web_context(items, start_index=citation_start)
    web_citations = build_web_citations(items, start_index=citation_start)
    return web_context, web_citations


def _resolve_kg_context(
    db: Session | None,
    user: User | None,
    message: str,
) -> KgQaContext | None:
    if db is None or user is None or not _kg_enabled_for_user(db, user):
        return None
    return retrieve_kg_context_for_question(db, user, message)


def _resolve_doc_retrieval(
    db: Session | None,
    user: User | None,
    message: str,
) -> tuple[str, list[dict]]:
    if db is None or user is None or not _knowledge_search_enabled(db, user):
        return "", []
    from app.services.document_service import list_queryable_documents
    from app.services.knowledge_qa_service import (
        _doc_citation_meta,
        _doc_titles,
        build_aligned_qa_context_and_citations,
        retrieve_hits_for_qa,
    )

    docs, _ = list_queryable_documents(
        db, user, page=1, page_size=_MAX_QUERYABLE_DOCS
    )
    doc_ids = [d.id for d in docs]
    if not doc_ids:
        return "", []
    hits, _mode = retrieve_hits_for_qa(db, user, doc_ids, message)
    if not hits:
        return "", []
    doc_titles = _doc_titles(db, doc_ids)
    doc_meta = _doc_citation_meta(db, doc_ids)
    return build_aligned_qa_context_and_citations(
        hits,
        doc_titles,
        question=message,
        doc_meta=doc_meta,
    )


def _attachment_file_count(
    db: Session | None,
    user: User | None,
    attachment_session_id: str | None,
) -> int:
    if db is None or user is None or not (attachment_session_id or "").strip():
        return 0
    from app.services.ai_chat_attachment_service import get_owned_session

    try:
        manifest = get_owned_session(user.id, attachment_session_id)
    except Exception:
        return 0
    return len(manifest.get("files") or [])


def _resolve_attachment_context(
    db: Session | None,
    user: User | None,
    attachment_session_id: str | None,
) -> tuple[str, int]:
    if db is None or user is None or not (attachment_session_id or "").strip():
        return "", 0
    from app.services.ai_chat_attachment_service import (
        build_attachment_context,
        get_owned_session,
    )

    try:
        manifest = get_owned_session(user.id, attachment_session_id)
    except Exception:
        return "", 0
    files = manifest.get("files") or []
    return build_attachment_context(files), len(files)


def _append_web_context(
    merged_context: str,
    citations: list[dict],
    *,
    web_context: str,
    web_citations: list[dict],
) -> tuple[str, list[dict]]:
    if not (web_context or "").strip():
        return merged_context, citations
    parts = [p.strip() for p in (merged_context, web_context) if (p or "").strip()]
    return "\n\n".join(parts), list(citations) + list(web_citations)


def _merge_retrieval_context(
    *,
    attachment_context: str,
    doc_context: str,
    doc_citations: list[dict],
    kg_context: KgQaContext | None,
) -> tuple[str, list[dict]]:
    merged_context, citations = merge_kg_qa_into_context(
        doc_context, doc_citations, kg_context
    )
    parts = [p.strip() for p in (attachment_context, merged_context) if (p or "").strip()]
    return "\n\n".join(parts), citations


def _effective_context_instruction(
    plan: AgentToolPlan,
    *,
    use_web_search: bool,
) -> str:
    if use_web_search and not plan.use_web_search:
        return (
            _MIXED_RETRIEVAL_WEB_INSTRUCTION
            if plan.use_doc_retrieval
            else _WEB_SEARCH_CONTEXT_INSTRUCTION
        )
    return plan.context_instruction


def _resolve_answer_context(
    db: Session | None,
    user: User | None,
    message: str,
    attachment_session_id: str | None = None,
    history: list[AiChatMessage] | None = None,
) -> tuple[str, list[dict], KgQaContext | None, int, AgentToolPlan, str]:
    attach_count = _attachment_file_count(db, user, attachment_session_id)
    kb_enabled = bool(
        db is not None
        and user is not None
        and _knowledge_search_enabled(db, user)
    )
    kg_enabled = bool(
        db is not None and user is not None and _kg_enabled_for_user(db, user)
    )
    web_enabled = _web_search_enabled(db)
    plan = _plan_agent_tools(
        message,
        attach_count=attach_count,
        kb_enabled=kb_enabled,
        kg_enabled=kg_enabled,
        web_enabled=web_enabled,
        history=history,
    )

    attachment_context = ""
    if plan.use_attachment:
        attachment_context, attach_count = _resolve_attachment_context(
            db, user, attachment_session_id
        )

    doc_context, doc_citations = "", []
    if plan.use_doc_retrieval:
        doc_context, doc_citations = _resolve_doc_retrieval(db, user, message)

    kg_context: KgQaContext | None = None
    if plan.use_kg:
        kg_context = _resolve_kg_context(db, user, message)

    use_web_search = plan.use_web_search
    if (
        not use_web_search
        and web_enabled
        and plan.use_doc_retrieval
        and not doc_citations
        and _web_search_fallback_after_empty_kb(message)
    ):
        use_web_search = True

    merged_context, citations = _merge_retrieval_context(
        attachment_context=attachment_context,
        doc_context=doc_context,
        doc_citations=doc_citations,
        kg_context=kg_context,
    )
    if use_web_search:
        web_context, web_citations = _resolve_web_search(
            db,
            message,
            citation_start=len(citations) + 1,
        )
        merged_context, citations = _append_web_context(
            merged_context,
            citations,
            web_context=web_context,
            web_citations=web_citations,
        )
    return (
        merged_context,
        citations,
        kg_context,
        attach_count,
        plan,
        _effective_context_instruction(plan, use_web_search=use_web_search),
    )


def _resolve_platform_knowledge(
    db: Session | None,
    user: User | None,
) -> str:
    if db is None or user is None:
        return ""
    from app.services.assistant_knowledge import build_platform_knowledge

    return build_platform_knowledge(db, user)


def _build_chat_messages(
    *,
    message: str,
    history: list[AiChatMessage],
    retrieval_context: str = "",
    platform_knowledge: str = "",
    context_instruction: str = _RETRIEVAL_CONTEXT_INSTRUCTION,
) -> list[dict]:
    system = _SYSTEM_PROMPT
    if platform_knowledge.strip():
        system = f"{system}\n\n【平台操作知识库】\n{platform_knowledge.strip()}"
    if retrieval_context.strip():
        instruction = (context_instruction or _RETRIEVAL_CONTEXT_INSTRUCTION).strip()
        system = f"{system}\n\n{instruction}\n\n{retrieval_context.strip()}"
    messages: list[dict] = [{"role": "system", "content": system}]
    tail = history[-_MAX_HISTORY:] if history else []
    for item in tail:
        messages.append({"role": item.role, "content": item.content.strip()})
    messages.append({"role": "user", "content": message.strip()})
    return messages


def _kg_meta_payload(kg_context: KgQaContext | None) -> dict[str, Any]:
    if not kg_context:
        return {}
    return {
        "kg_matched_entities": len(kg_context.matched_entity_ids),
        "kg_entity_count": kg_context.entity_count,
        "kg_relation_count": kg_context.relation_count,
    }


_step_seq = 0


def _next_step_id() -> str:
    global _step_seq
    _step_seq += 1
    return f"ai-s{_step_seq}"


def _workflow_event(
    phase: str,
    *,
    title: str,
    detail: str = "",
    tool: str = "",
    status: str = "running",
    step_id: str = "",
) -> str:
    ev: dict[str, Any] = {"phase": phase, "title": title, "status": status}
    if detail:
        ev["detail"] = detail
    if tool:
        ev["tool"] = tool
    if step_id:
        ev["step_id"] = step_id
    return json.dumps({"workflow": ev}, ensure_ascii=False)


async def _emit_workflow(phase: str, **kwargs: Any) -> AsyncIterator[str]:
    yield _workflow_event(phase, **kwargs)
    await asyncio.sleep(0)


def _persist_turn(
    db: Session | None,
    *,
    user_id: uuid.UUID | None,
    conversation_id: str | None,
    message: str,
    reply: str,
) -> str | None:
    if db is None or user_id is None:
        return conversation_id
    conv = platform_chat_store.get_or_create_conversation(
        db,
        user_id=user_id,
        scope="ai-home",
        conversation_id=conversation_id,
    )
    platform_chat_store.append_turn(
        db,
        conversation=conv,
        user_message=message,
        assistant_message=reply,
    )
    db.commit()
    return str(conv.id)


async def iter_chat_with_ai_agent_stream(
    *,
    message: str,
    history: list[AiChatMessage],
    db: Session | None = None,
    user: User | None = None,
    conversation_id: str | None = None,
    attachment_session_id: str | None = None,
) -> AsyncIterator[str]:
    """逐块产出 SSE data 行（不含 event: 前缀，由 API 层包装）。"""
    if not is_configured():
        yield json.dumps({"error": "AI 对话未配置，请联系管理员配置 DeepSeek API"}, ensure_ascii=False)
        return

    async for payload in _emit_workflow("workflow_started", title="开始处理问题"):
        yield payload

    think_id = _next_step_id()
    async for payload in _emit_workflow(
        "agent_thinking",
        title="分析问题意图",
        detail=message.strip()[:160],
        step_id=think_id,
    ):
        yield payload
    async for payload in _emit_workflow(
        "agent_thought",
        title="已理解问题",
        detail="准备处理用户问题",
        step_id=think_id,
        status="done",
    ):
        yield payload

    doc_context = ""
    doc_citations: list[dict] = []
    attachment_context = ""
    attach_count = _attachment_file_count(db, user, attachment_session_id)

    kb_enabled = bool(
        db is not None
        and user is not None
        and _knowledge_search_enabled(db, user)
    )
    kg_enabled = bool(
        db is not None and user is not None and _kg_enabled_for_user(db, user)
    )
    web_enabled = _web_search_enabled(db)
    plan = _plan_agent_tools(
        message,
        attach_count=attach_count,
        kb_enabled=kb_enabled,
        kg_enabled=kg_enabled,
        web_enabled=web_enabled,
        history=history,
    )

    async for payload in _emit_workflow(
        "agent_thought",
        title="已选择处理方式",
        detail=plan.intent_label,
        step_id=think_id,
        status="done",
    ):
        yield payload

    attach_id = _next_step_id()
    if plan.use_attachment and db is not None and user is not None:
        async for payload in _emit_workflow(
            "tool_call",
            title="读取临时附件",
            tool="attachments",
            detail=message.strip()[:120],
            step_id=attach_id,
        ):
            yield payload
        attachment_context, attach_count = _resolve_attachment_context(
            db, user, attachment_session_id
        )
        attach_detail = (
            f"已加载 {attach_count} 个附件"
            if attach_count
            else "未找到有效附件"
        )
        async for payload in _emit_workflow(
            "tool_result",
            title="临时附件就绪",
            tool="attachments",
            detail=attach_detail,
            step_id=attach_id,
            status="done",
        ):
            yield payload

    retrieve_id = _next_step_id()
    if plan.use_doc_retrieval and db is not None and user is not None:
        async for payload in _emit_workflow(
            "tool_call",
            title="检索权限内文档",
            tool="retrieve",
            detail=message.strip()[:120],
            step_id=retrieve_id,
        ):
            yield payload
        doc_context, doc_citations = _resolve_doc_retrieval(db, user, message)
        retrieve_detail = (
            f"命中 {len(doc_citations)} 条相关片段"
            if doc_citations
            else "未命中相关文档片段"
        )
        async for payload in _emit_workflow(
            "tool_result",
            title="文档检索完成",
            tool="retrieve",
            detail=retrieve_detail,
            step_id=retrieve_id,
            status="done",
        ):
            yield payload

    kg_context: KgQaContext | None = None
    kg_id = _next_step_id()
    if plan.use_kg and db is not None and user is not None:
        async for payload in _emit_workflow(
            "tool_call",
            title="解析本体图谱关联",
            tool="kg_context",
            detail=message.strip()[:120],
            step_id=kg_id,
        ):
            yield payload
        kg_context = _resolve_kg_context(db, user, message)
        if kg_context and kg_context.context_text.strip():
            kg_detail = (
                f"匹配 {len(kg_context.matched_entity_ids)} 个实体，"
                f"{kg_context.relation_count} 条关系"
            )
        else:
            kg_detail = "未匹配到相关实体"
        async for payload in _emit_workflow(
            "tool_result",
            title="本体图谱上下文",
            tool="kg_context",
            detail=kg_detail,
            step_id=kg_id,
            status="done",
        ):
            yield payload

    use_web_search = plan.use_web_search
    if (
        not use_web_search
        and web_enabled
        and plan.use_doc_retrieval
        and not doc_citations
        and _web_search_fallback_after_empty_kb(message)
    ):
        use_web_search = True

    merged_context, citations = _merge_retrieval_context(
        attachment_context=attachment_context,
        doc_context=doc_context,
        doc_citations=doc_citations,
        kg_context=kg_context,
    )

    context_instruction = plan.context_instruction
    if use_web_search and not plan.use_web_search:
        context_instruction = _effective_context_instruction(
            plan, use_web_search=use_web_search
        )

    web_id = _next_step_id()
    if use_web_search:
        async for payload in _emit_workflow(
            "tool_call",
            title="联网检索相关资料",
            tool="web_search",
            detail=message.strip()[:120],
            step_id=web_id,
        ):
            yield payload
        web_context, web_citations = _resolve_web_search(
            db,
            message,
            citation_start=len(citations) + 1,
        )
        merged_context, citations = _append_web_context(
            merged_context,
            citations,
            web_context=web_context,
            web_citations=web_citations,
        )
        web_detail = (
            f"获取 {len(web_citations)} 条联网摘要"
            if web_citations
            else "未获取到有效联网结果"
        )
        async for payload in _emit_workflow(
            "tool_result",
            title="联网检索完成",
            tool="web_search",
            detail=web_detail,
            step_id=web_id,
            status="done",
        ):
            yield payload

    async for payload in _emit_workflow("node_started", title="正在生成回答"):
        yield payload

    accumulated = ""
    platform_knowledge = _resolve_platform_knowledge(db, user)
    messages = _build_chat_messages(
        message=message,
        history=history,
        retrieval_context=merged_context,
        platform_knowledge=platform_knowledge,
        context_instruction=context_instruction,
    )
    api_key, base_url, model = resolve_credentials()
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.6,
        "stream": True,
    }
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as r:
                if r.status_code >= 400:
                    body = (await r.aread())[:500].decode("utf-8", errors="replace")
                    yield json.dumps(
                        {"error": f"AI 对话暂时不可用: {body}"},
                        ensure_ascii=False,
                    )
                    async for payload in _emit_workflow(
                        "workflow_finished", title="处理失败", status="failed"
                    ):
                        yield payload
                    return
                async for line in r.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                    text = delta.get("content") or ""
                    if text:
                        accumulated += text
                        yield json.dumps({"delta": text}, ensure_ascii=False)
        out_conv_id = _persist_turn(
            db,
            user_id=user.id if user else None,
            conversation_id=conversation_id,
            message=message,
            reply=accumulated,
        )
        from app.services.knowledge_qa_service import finalize_citations_preserving_index

        display_citations: list[dict] = []
        normalized_answer = accumulated
        if citations:
            normalized_answer, display_citations = finalize_citations_preserving_index(
                accumulated, citations
            )
        done_payload: dict[str, Any] = {
            "done": True,
            "model": model,
            "reply": normalized_answer,
            "conversation_id": out_conv_id,
            **_kg_meta_payload(kg_context),
        }
        if display_citations:
            yield json.dumps({"citations": display_citations}, ensure_ascii=False)
            done_payload["citations"] = display_citations
        yield json.dumps(done_payload, ensure_ascii=False)
        async for payload in _emit_workflow("workflow_finished", title="完成"):
            yield payload
    except httpx.HTTPError as e:
        yield json.dumps({"error": f"无法连接 AI 服务: {e}"}, ensure_ascii=False)
        async for payload in _emit_workflow(
            "workflow_finished", title="处理失败", status="failed"
        ):
            yield payload


async def chat_with_ai_agent(
    *,
    message: str,
    history: list[AiChatMessage],
    db: Session | None = None,
    user: User | None = None,
    conversation_id: str | None = None,
    attachment_session_id: str | None = None,
) -> dict:
    if not is_configured():
        raise bad_request("AI 对话未配置，请联系管理员配置 DeepSeek API")

    retrieval_context, citations, kg_context, _attach_count, plan, context_instruction = (
        _resolve_answer_context(
            db, user, message, attachment_session_id, history=history
        )
    )
    platform_knowledge = _resolve_platform_knowledge(db, user)
    messages = _build_chat_messages(
        message=message,
        history=history,
        retrieval_context=retrieval_context,
        platform_knowledge=platform_knowledge,
        context_instruction=context_instruction,
    )
    api_key, base_url, model = resolve_credentials()
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.6,
    }
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:500] if e.response is not None else str(e)
        raise bad_request(f"AI 对话暂时不可用: {detail}") from e
    except httpx.HTTPError as e:
        raise bad_request(f"无法连接 AI 服务: {e}") from e

    choices = body.get("choices") or []
    if not choices:
        raise bad_request("AI 返回为空")
    reply = (choices[0].get("message", {}) or {}).get("content") or ""
    reply = reply.strip()
    if not reply:
        raise bad_request("AI 返回为空")
    out_conv_id = _persist_turn(
        db,
        user_id=user.id if user else None,
        conversation_id=conversation_id,
        message=message,
        reply=reply,
    )
    from app.services.knowledge_qa_service import finalize_citations_preserving_index

    display_citations: list[dict] = []
    normalized_reply = reply
    if citations:
        normalized_reply, display_citations = finalize_citations_preserving_index(
            reply, citations
        )
    result: dict[str, Any] = {
        "reply": normalized_reply,
        "model": model,
        "conversation_id": out_conv_id,
        **_kg_meta_payload(kg_context),
    }
    if display_citations:
        result["citations"] = display_citations
    return result
