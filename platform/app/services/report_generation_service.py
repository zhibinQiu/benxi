"""报告生成 Agent：联网检索 + 本地知识库 + LLM 综合撰写。"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.chat_context import trim_chat_history
from app.core.prompt_budget import (
    fit_messages_to_total_budget,
    get_prompt_limits,
    truncate_to_budget,
)
from app.integrations.deepseek_client import is_configured, resolve_credentials
from app.core.platform_assistant import assistant_report_persona
from app.models.org import User
from app.schemas.ai_chat import AiChatMessage
from app.services import platform_chat_store
from app.services.knowledge_qa_service import (
    _citation_image_id,
    _citation_preview_available,
    build_citations,
    finalize_citations_for_display,
)
from app.services.searxng_service import (
    is_enabled as searxng_enabled,
)

logger = logging.getLogger(__name__)

_MAX_HISTORY = 16
_MAX_WEB_RESULTS = 10

# 报告生成：多路召回、保留更多片段（知识检索默认仅 5 条且合并邻近块）
_PER_QUERY_LOCAL_HITS = 15
_MAX_LOCAL_CHUNKS = 28
_MAX_CHARS_PER_CHUNK = 1600
_MAX_LOCAL_CONTEXT_CHARS = get_prompt_limits()["report_context_max_chars"]

_FORMAT_HINTS = (
    "格式",
    "排版",
    "大纲",
    "目录",
    "表格",
    "精简",
    "重排",
    "改成",
    "调整为",
    "换用",
    "markdown",
    "word",
    "ppt",
    "Executive Summary",
)

_FORMAT_PATTERNS = (
    r"(?:报告|正文|内容)?(?:的)?(?:格式|排版|结构|布局)",
    r"(?:改成|调整为|换用|转为|换成).{0,10}(?:表格|条目|列表|markdown|word|ppt)",
    r"(?:重排|重写|改写).{0,8}(?:大纲|目录|结构)",
    r"Executive Summary",
    r"(?:精简|压缩|缩短).{0,8}(?:篇幅|字数|长度|报告)",
    r"(?:一级|二级|三级)?标题(?:层级|结构)",
)

_SUPPLEMENT_PATTERNS = (
    r"补充|增补|添加|增加|加上|纳入",
    r"扩写|展开|详细|深入|丰富|更多",
    r"案例|实例|数据|证据|政策|趋势",
    r"海外|国内|最新|近期",
    r"第三(?:章|部分)|结论|摘要",
    r"修正|纠正|更新|修订",
)

# 与知识检索（归纳式短答）不同：报告生成强调大量吸收原文并扩写整合。
_REPORT_SYSTEM = f"""{assistant_report_persona()}。你的任务不是像问答助手那样给出简短归纳，而是撰写一份内容充实的长报告。

与「知识检索问答」的本质区别：
- 知识检索：用少量片段做归纳总结，回答要精炼
- 报告生成：从材料中大量取材，改写、扩写、重组后写入报告正文，篇幅应明显长于材料摘要

写作原则：
1. **大量取材**：下方编号材料块是已召回的原文，应尽可能多地被吸收进报告各章节
2. **扩写整合**：在忠实于材料含义的前提下解释、展开与衔接；不得编造材料中不存在的数据、文号或结论
3. **结构化长文**：使用 Markdown 标题；首次生成建议含摘要、背景、分主题分析、结论与建议
4. **引用编号（极其重要）**：
   - 仅能在句末用 [1]、[2] 标注；编号必须与下方材料块 [n] **严格一一对应**，不得张冠李戴
   - 每个 [n] 只能标注确实来自该编号块的事实；不确定时不要标注
   - 界面底部会展示本次检索到的全部材料来源；请在引用材料的句末尽量标注 [n]
5. **禁止来源叙述**：正文不得出现文档名、书名、网页名、URL、「根据…」「参考了…」「据…显示」「数据来源」「参考来源」「参考文献」等；**不要单独写来源说明章节**，溯源只通过 [n] 完成
6. **信息源优先级（冲突时必须遵守）**：
   - **优先级 1 · 本地知识库**：本地编号材料中的事实、数据、日期、政策表述为最高依据
   - **优先级 2 · 联网检索**：仅在不与本地材料冲突时采用；若与本地冲突，**以本地为准**，联网内容不得覆盖本地结论
   - **优先级 3 · 模型自身知识**：仅用于填补材料空白、过渡衔接与背景解释；**不得**改写、否定或替换前两者的关键事实；无编号材料支撑的具体数据/结论不要写入
   - 联网与模型知识冲突时，以联网编号材料为准
7. **不足即说明**：材料不够时标注「待补充」，勿虚构
8. **语言风格（像人写的报告，不要 AI 腔）**：
   - 采用专业、自然的中文研究报告写法，段落长短有变化，像机构内部分析稿而非对话式 AI 输出
   - **禁止套话与机械收束**：不得使用「综上所述」「总结如下」「小结如下」「总而言之」「总的来说」「概括而言」「不难看出」「由此可见」「需要注意的是」「值得一提的是」「不可否认」「在这个背景下」「随着…的不断发展」「一方面…另一方面…」「本文将…」「旨在…」「致力于…」「具有十分重要的意义」「至关重要」「赋能」「助力」等
   - **禁止英译中/欧化表达**：避免翻译腔与英文句式直译，例如「进行讨论/分析/研究」（改说「讨论/分析/研究」）、「通过…的方式」「在…方面」「使得…」「被…所…」「就…而言（滥用）」「从…角度来看（空泛时）」「这一举措/此举」「与此同时/此外/然而」连续堆砌、过长定语链、被动句连用；优先用**中文短句、主动语态、直述事实**
   - 章节之间用事实与逻辑自然衔接，**不要**每节末尾写「总结如下：…」式归纳句；结论章也要具体，不要空泛拔高

禁止：高度概括短答、压缩材料为几句结论、在正文描述引用了哪些文档或网页、用低优先级来源覆盖高优先级来源、AI 套话与翻译腔、章节末尾机械总结。"""

_SOURCE_PRIORITY_RULE = (
    "信息源优先级（内容冲突时严格执行，低优先级不得覆盖高优先级）：\n"
    "1. 本地知识库编号材料（最高）\n"
    "2. 联网检索编号材料\n"
    "3. 模型自身知识（仅补全空白与过渡，勿改写前两者的关键事实；此类内容不要标注 [n]）"
)

_REPORT_CITATION_RULE = (
    "下方编号材料仅供写作取材与句末 [n] 标注，编号与块序号严格对应。"
    "本地材料编号在前、联网材料编号在后；冲突时以本地为准。"
    "勿在正文中提及材料来源名称或类型。"
)

_INTENT_LABELS = {
    "initial": "报告生成",
    "follow_up": "补充与修订",
    "format_adjust": "调整报告格式",
}

_REPORT_ASPECT_SUFFIXES = (
    "背景与定义",
    "现状与数据",
    "问题与挑战",
    "政策与趋势",
    "案例与实践",
    "对策与建议",
)

REPORT_OPTIMIZE_PRESETS: dict[str, dict[str, str]] = {
    "expand": {
        "label": "扩写充实",
        "description": "补充细节、论据与背景说明",
        "prompt": "请在现有报告基础上扩写充实，补充细节、背景说明与论据，保持原有结构与引用编号；"
        "若新检索材料与旧报告冲突，以本地知识库 > 联网检索 > 模型知识的优先级为准。",
    },
    "shorten": {
        "label": "精简压缩",
        "description": "删繁就简，保留核心结论",
        "prompt": "请精简报告篇幅，保留核心论点、关键数据与结论，删除重复表述。",
    },
    "add_cases": {
        "label": "补充案例",
        "description": "增加实践案例与应用场景",
        "prompt": "请补充典型应用案例、实践经验与场景化说明，句末用 [n] 标注出处。",
    },
    "executive_summary": {
        "label": "执行摘要",
        "description": "在文首增加 Executive Summary",
        "prompt": "请在报告文首增加 Executive Summary（约 200 字），概括背景、发现与建议。",
    },
    "table_format": {
        "label": "表格呈现",
        "description": "关键对比改为表格",
        "prompt": "请将报告中适合对比的内容改为 Markdown 表格呈现，其余章节保持不变。",
    },
    "formal_polish": {
        "label": "正式润色",
        "description": "优化表述，更正式连贯",
        "prompt": "请润色全文表述，使语气更正式、逻辑更连贯，不改变事实与引用编号含义；"
        "去除 AI 套话（如「综上所述」「总结如下」）与英译中腔调，保持自然中文报告语感。",
    },
    "add_recommendations": {
        "label": "强化建议",
        "description": "扩展结论与行动建议",
        "prompt": "请扩展「结论与建议」章节，增加可落地的行动建议与风险提示。",
    },
}


def list_optimize_presets() -> list[dict[str, str]]:
    return [
        {
            "id": key,
            "label": meta["label"],
            "description": meta["description"],
            "prompt": meta["prompt"],
        }
        for key, meta in REPORT_OPTIMIZE_PRESETS.items()
    ]


def _pattern_score(text: str, patterns: tuple[str, ...]) -> int:
    score = 0
    for pattern in patterns:
        if re.search(pattern, text, flags=re.I):
            score += 1
    return score


def _has_prior_assistant_turn(history: list[AiChatMessage]) -> bool:
    """是否存在已完成的上轮助手回复（不含当前用户输入）。"""
    return any(
        m.role == "assistant" and (m.content or "").strip()
        for m in history
    )


def _first_user_message(history: list[AiChatMessage]) -> str:
    for item in history:
        if item.role == "user" and (item.content or "").strip():
            return item.content.strip()
    return ""


def _last_assistant_message(history: list[AiChatMessage]) -> str:
    for item in reversed(history):
        if item.role == "assistant" and (item.content or "").strip():
            return item.content.strip()
    return ""


def resolve_report_topic(message: str, history: list[AiChatMessage] | None = None) -> str:
    """解析报告主题：追问时优先沿用首轮用户需求，避免短句被误当主题。"""
    hist = history or []
    first_user = _first_user_message(hist)
    if first_user:
        topic = extract_report_topic(first_user)
        if topic:
            return topic
    topic = extract_report_topic(message)
    if topic:
        return topic
    if first_user:
        return first_user[:120]
    return (message or "").strip()[:120]


def _intent_context_text(message: str, history: list[AiChatMessage]) -> str:
    """综合最近对话构建意图识别上下文（适配短追问）。"""
    parts: list[str] = []
    current = (message or "").strip()
    if current:
        parts.append(f"当前输入：{current}")
    first_user = _first_user_message(history)
    if first_user and first_user != current:
        parts.append(f"首轮需求：{first_user}")
    last_reply = _last_assistant_message(history)
    if last_reply:
        snippet = last_reply[:1200]
        if len(last_reply) > 1200:
            snippet += "…"
        parts.append(f"上一版报告摘要：{snippet}")
    return "\n".join(parts)


def classify_intent(
    message: str,
    *,
    has_history: bool,
    history: list[AiChatMessage] | None = None,
) -> str:
    text = (message or "").strip()
    if not text:
        return "initial"
    if not has_history:
        return "initial"

    hist = history or []
    ctx = _intent_context_text(text, hist)
    classify_text = text if len(text) >= 20 else ctx
    if len(text) < 20 and text not in classify_text:
        classify_text = f"{ctx}\n{text}"

    lowered = classify_text.lower()
    format_score = _pattern_score(classify_text, _FORMAT_PATTERNS)
    supplement_score = _pattern_score(classify_text, _SUPPLEMENT_PATTERNS)

    if any(h.lower() in lowered for h in _FORMAT_HINTS):
        format_score += 1

    if re.search(r"^(请)?(把|将)?报告", text) and re.search(
        r"(格式|结构|排版|表格|目录|大纲)", text
    ):
        format_score += 2

    # 短句「表格/目录/摘要」等，结合上下文判断为格式调整
    if len(text) <= 16 and re.search(r"(格式|结构|排版|表格|目录|大纲|摘要|markdown|word)", text, re.I):
        format_score += 2

    if format_score > 0 and format_score >= supplement_score:
        return "format_adjust"
    if supplement_score > 0:
        return "follow_up"
    if re.search(r"修改|修订|调整|优化|完善|继续|补充|扩写|追加|再加", classify_text):
        return "follow_up"
    if len(text) <= 12 and _has_prior_assistant_turn(hist):
        return "follow_up"
    return "follow_up"


def extract_report_topic(message: str) -> str:
    text = " ".join((message or "").strip().split())
    if not text:
        return ""
    patterns = (
        r"^(?:请|帮我|麻烦)?(?:写|生成|撰写|整理|输出)(?:一份|一个|一篇)?(?:关于)?[「\"『]?(.+?)[」\"』]?(?:的)?(?:研究)?报告(?:吧|。)?$",
        r"^(?:关于|针对)[「\"『]?(.+?)[」\"』]?(?:的)?(?:研究)?报告",
        r"^(.+?)(?:研究)?报告(?:撰写|生成|整理)?$",
    )
    for pattern in patterns:
        m = re.match(pattern, text, flags=re.I)
        if m:
            topic = m.group(1).strip(" ：:，,")
            if topic:
                return topic
    return text[:120]


def build_search_queries(message: str, *, topic: str, intent: str) -> list[str]:
    base = topic or extract_report_topic(message) or message.strip()
    queries = [base]
    if intent == "follow_up" and base != message.strip():
        queries.append(message.strip()[:120])
    seen: set[str] = set()
    ordered: list[str] = []
    for q in queries:
        key = q.lower()
        if key and key not in seen:
            seen.add(key)
            ordered.append(q)
    return ordered[:3]


def build_local_retrieval_queries(
    message: str,
    *,
    topic: str,
    intent: str,
    history: list[AiChatMessage] | None = None,
) -> list[str]:
    """多路召回查询：报告需覆盖多个子主题，而非单问单答。"""
    base = topic or extract_report_topic(message) or message.strip()
    current = message.strip()
    queries: list[str] = []
    if base:
        queries.append(base)
    if intent == "initial" and topic:
        for suffix in _REPORT_ASPECT_SUFFIXES:
            queries.append(f"{topic} {suffix}")
    elif intent == "follow_up":
        queries.append(current[:160])
        if base:
            queries.append(f"{base} {current[:80]}")
            queries.append(base)
        last_report = _last_assistant_message(history or [])
        if last_report and len(current) <= 24:
            heading = re.search(r"^#{1,3}\s+(.+)$", last_report, re.M)
            if heading:
                queries.append(f"{base} {heading.group(1).strip()[:40]}")
    else:
        queries.append(current[:160])

    seen: set[str] = set()
    ordered: list[str] = []
    for q in queries:
        key = q.lower()
        if key and key not in seen:
            seen.add(key)
            ordered.append(q)
    return ordered[:6]


def _hit_dedupe_key(hit: dict) -> str:
    chunk_id = hit.get("chunk_id")
    if chunk_id:
        return f"chunk:{chunk_id}"
    did = str(hit.get("document_id") or "")
    page = (hit.get("anchor_json") or {}).get("page")
    body = (hit.get("content") or hit.get("snippet") or "")[:96]
    return f"{did}:{page}:{body}"


def merge_retrieval_hits(hits: list[dict], *, max_total: int) -> list[dict]:
    """按 score 去重合并多路召回，保留尽可能多的不同片段。"""

    def _preview_rank(h: dict) -> int:
        if _citation_preview_available(h):
            return 2
        if _citation_image_id(h):
            return 1
        return 0

    best: dict[str, dict] = {}
    order: list[str] = []
    for h in hits:
        key = _hit_dedupe_key(h)
        prev = best.get(key)
        if prev is None:
            best[key] = h
            order.append(key)
            continue
        h_score = float(h.get("score") or 0)
        p_score = float(prev.get("score") or 0)
        if h_score > p_score or (
            h_score == p_score and _preview_rank(h) > _preview_rank(prev)
        ):
            best[key] = h
    merged = [best[k] for k in order]
    merged.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
    return merged[:max_total]


def retrieve_local_hits_for_report(
    db: Session,
    user: User,
    doc_ids: list[uuid.UUID],
    queries: list[str],
) -> list[dict]:
    from app.services.knowledge_qa_service import retrieve_merged_hits_for_queries

    return retrieve_merged_hits_for_queries(
        db,
        user,
        doc_ids,
        queries,
        limit_per_query=_PER_QUERY_LOCAL_HITS,
        merge_nearby=False,
        max_total=_MAX_LOCAL_CHUNKS,
    )


def _strip_html_tags(text: str) -> str:
    return re.sub(r"</?(?:em|mark|font)[^>]*>", "", text, flags=re.I)


def _extract_hit_body(hit: dict, *, max_chars: int = _MAX_CHARS_PER_CHUNK) -> str:
    for key in ("content", "highlight", "snippet"):
        raw = (hit.get(key) or "").strip()
        if not raw:
            continue
        body = _strip_html_tags(raw)
        if len(body) > max_chars:
            return body[: max_chars - 1] + "…"
        return body
    return ""


def build_report_context_block(
    hits: list[dict],
    doc_titles: dict[str, str],
    *,
    max_total_chars: int = _MAX_LOCAL_CONTEXT_CHARS,
) -> str:
    """构建供 LLM 扩写用的长片段上下文（保留更多原文，非摘要）。"""
    local, _, _, _ = build_aligned_report_sources(
        hits,
        doc_titles,
        [],
        max_total_chars=max_total_chars,
    )
    return local


def build_aligned_report_sources(
    hits: list[dict],
    doc_titles: dict[str, str],
    web_items: list[dict],
    *,
    question: str = "",
    max_total_chars: int = _MAX_LOCAL_CONTEXT_CHARS,
) -> tuple[str, str, list[dict], int]:
    """构建与 citations 索引严格对齐的材料块与引用列表。"""
    included_hits: list[dict] = []
    blocks: list[str] = []
    used = 0

    for h in hits:
        body = _extract_hit_body(h)
        if not body:
            continue
        idx = len(included_hits) + 1
        block = f"[{idx}]\n{body}"
        if used + len(block) > max_total_chars:
            remaining = max_total_chars - used
            if remaining < 200:
                break
            block = block[: remaining - 1] + "…"
            blocks.append(block)
            included_hits.append(h)
            break
        blocks.append(block)
        included_hits.append(h)
        used += len(block) + 2

    local_context = "\n\n".join(blocks)
    local_citations = build_citations(
        included_hits,
        doc_titles,
        question=question,
    )
    for row in local_citations:
        row["source"] = row.get("source") or "local"

    web_start = len(included_hits) + 1
    web_context = _format_web_context(web_items, start_index=web_start)
    web_citations = build_web_citations(web_items, start_index=web_start)
    all_citations = list(local_citations) + list(web_citations)
    return local_context, web_context, all_citations, len(included_hits)


def finalize_report_citations(
    answer: str,
    citations: list[dict],
) -> tuple[str, list[dict]]:
    """报告专用：仅保留正文 [n] 实际引用的条目。"""
    return finalize_citations_for_display(answer, citations)


def _parse_document_ids(raw: list[str] | None) -> list[uuid.UUID]:
    out: list[uuid.UUID] = []
    for item in raw or []:
        try:
            out.append(uuid.UUID(str(item)))
        except ValueError:
            continue
    return out[:20]


def _format_web_context(items: list[dict], *, start_index: int) -> str:
    if not items:
        return ""
    blocks: list[str] = []
    for i, row in enumerate(items, start=start_index):
        snippet = (row.get("snippet") or "").strip()
        if snippet:
            blocks.append(f"[{i}]\n{snippet}")
    return "\n\n".join(blocks)


def build_web_citations(items: list[dict], *, start_index: int = 1) -> list[dict]:
    citations: list[dict] = []
    for i, row in enumerate(items, start=start_index):
        citations.append(
            {
                "index": i,
                "title": (row.get("title") or "网页").strip(),
                "snippet": (row.get("snippet") or "")[:2000],
                "url": (row.get("url") or "").strip() or None,
                "source": "web",
                "document_id": None,
                "preview_available": False,
            }
        )
    return citations


def _merge_citations(local: list[dict], web: list[dict]) -> list[dict]:
    """保留兼容；新逻辑请用 build_aligned_report_sources。"""
    return list(local) + list(web)


def _intent_instruction(intent: str, *, chunk_count: int) -> str:
    if intent == "format_adjust":
        return (
            "用户希望调整已有报告的格式或结构。请主要依据对话中的上一版报告内容进行重写，"
            "除非用户明确要求补充新信息。"
        )
    if intent == "follow_up":
        return (
            "用户在已有报告基础上追问或要求补充。请**结合对话历史中的上一版完整报告正文**、"
            "用户本轮输入与下方新检索材料，输出**完整修订后的报告**（不是只回复差异段落或简短说明）。"
            "对新增或修订内容在句末标注 [n]；底部引用区会展示材料来源，正文勿写文档名。"
            "若新材料与旧报告或不同来源冲突，按优先级处理：本地知识库 > 联网检索 > 模型知识。"
        )
    material_hint = (
        f"已从本地知识库召回 {chunk_count} 段原文片段，"
        "请尽量让多数片段在报告正文中得到体现与扩写；"
        "与联网或模型知识冲突时以本地片段为准。"
        if chunk_count
        else "本次未选本地文档或未命中片段，请主要依据联网材料撰写；"
        "联网与模型知识冲突时以联网为准；模型知识仅作空白补全。"
    )
    return (
        "用户希望生成一份新的研究报告。请输出完整、篇幅充足的长报告，"
        f"{material_hint}"
    )


def _build_messages(
    *,
    message: str,
    history: list[AiChatMessage],
    intent: str,
    topic: str,
    local_context: str,
    web_context: str,
    web_enabled: bool,
    local_enabled: bool,
    chunk_count: int,
    insufficient_note: str | None = None,
    local_searched: bool = False,
    web_searched: bool = False,
) -> list[dict]:
    limits = get_prompt_limits()
    local_context = truncate_to_budget(local_context, limits["report_context_max_chars"] // 2)
    web_context = truncate_to_budget(web_context, limits["report_context_max_chars"] // 2)
    message = truncate_to_budget(message.strip(), limits["user_max_chars"])

    parts = [_REPORT_SYSTEM, _intent_instruction(intent, chunk_count=chunk_count)]
    if insufficient_note:
        parts.append(
            "【材料不足】当前召回材料可能不足以完整撰写报告。"
            f"不足方面：{insufficient_note}。"
            "请基于已有编号材料尽力撰写；对缺失部分在相应章节标注「待补充」，"
            "并在报告末尾用一小段友好提示用户可补充哪些具体信息（如数据口径、时间范围、案例），"
            "不要编造缺失的具体数据或政策文号。"
        )
    if topic:
        parts.append(f"报告主题：{topic}")
    if intent in ("follow_up", "format_adjust") and _has_prior_assistant_turn(history):
        parts.append(
            "多轮说明：对话历史中 role=assistant 的消息为上一版报告正文；"
            "请在其基础上理解用户本轮意图并输出完整报告稿。"
        )

    source_notes: list[str] = [_SOURCE_PRIORITY_RULE]
    if local_context or web_context:
        source_notes.append(_REPORT_CITATION_RULE)
    if local_context:
        source_notes.append("【编号材料 · 本地知识库 · 优先级 1】\n" + local_context)
    elif local_enabled and local_searched:
        source_notes.append("【本地知识库 · 优先级 1】未命中相关内容。")
    if web_context:
        source_notes.append("【编号材料 · 联网检索 · 优先级 2】\n" + web_context)
    elif web_enabled and web_searched:
        source_notes.append("【联网检索 · 优先级 2】未获取到有效结果或未配置搜索服务。")
    if not local_context and not web_context:
        source_notes.append(
            "【模型知识 · 优先级 3】当前无本地/联网编号材料，可主要依据模型知识撰写，"
            "但须在文中说明材料局限，且勿编造具体数据或文号。"
        )
    if source_notes:
        parts.append("\n\n".join(source_notes))

    system = "\n\n".join(parts)
    messages: list[dict] = [{"role": "system", "content": system}]
    history_chars = max(8000, limits["report_prompt_max_chars"] // 2)
    tail = trim_chat_history(
        history,
        max_messages=_MAX_HISTORY,
        max_chars=history_chars,
    )
    for item in tail:
        messages.append({"role": item.role, "content": item.content.strip()})
    messages.append({"role": "user", "content": message})
    return fit_messages_to_total_budget(messages, limits["report_prompt_max_chars"])


def _report_web_on(db: Session, use_web_search: bool) -> bool:
    return bool(use_web_search and searxng_enabled(db))


async def _iter_llm_stream(*, messages: list[dict], intent: str) -> AsyncIterator[str]:
    """保留兼容：仅产出正文 delta。"""
    from app.services.llm_workflow_stream import iter_llm_answer_events

    limits = get_prompt_limits()
    temperature = 0.35 if intent == "format_adjust" else 0.55
    async for ev in iter_llm_answer_events(
        messages=messages,
        temperature=temperature,
        think_title="正在撰写报告",
        think_detail="整合材料并生成报告正文…",
        unlimited_output=True,
        max_total_chars=limits["report_prompt_max_chars"],
    ):
        if ev.get("type") == "delta" and ev.get("text"):
            yield ev["text"]


def _persist_turn(
    db: Session,
    *,
    user_id: uuid.UUID,
    conversation_id: str | None,
    message: str,
    reply: str,
) -> str:
    conv = platform_chat_store.get_or_create_conversation(
        db,
        user_id=user_id,
        scope="report-generation",
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


def get_meta(db: Session | None = None) -> dict[str, Any]:
    configured = is_configured()
    web_on = searxng_enabled(db)
    hint = ""
    if not configured:
        hint = "未配置 DeepSeek API，请联系管理员"
    elif not web_on:
        hint = "联网搜索未配置，将仅使用模型知识与本地知识库"
    return {
        "configured": configured,
        "web_search_enabled": web_on,
        "service_hint": hint,
    }


def import_report_to_library(
    db: Session,
    user: User,
    *,
    title: str,
    markdown: str,
    sync_knowflow: bool = True,
) -> dict[str, Any]:
    """将报告正文导出为 Word 并写入个人级文档库（默认未分类）。"""
    from app.core.document_scope import content_subscription_import_scope
    from app.core.exceptions import bad_request
    from app.core.platform_cache import invalidate_document_caches
    from app.integrations.markdown_docx_export import (
        build_docx_download_filename,
        markdown_to_docx_bytes,
    )
    from app.services.document_service import create_document, create_initial_uploaded_version

    safe_title = (title or "研究报告").strip()[:500] or "研究报告"
    try:
        content = markdown_to_docx_bytes(title=safe_title, markdown_text=markdown)
    except Exception as exc:
        raise bad_request(f"Word 生成失败: {exc}") from exc

    doc = create_document(
        db,
        user,
        title=safe_title,
        description="由报告生成导入",
        scope=content_subscription_import_scope(),
        folder_id=None,
    )
    create_initial_uploaded_version(
        db,
        doc,
        user,
        file_name=build_docx_download_filename(safe_title),
        mime_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        content=content,
    )
    db.commit()
    db.refresh(doc)

    knowflow_synced = False
    if sync_knowflow:
        from app.domains.knowledge.gateway import knowledge
        from app.services.document_service import resolve_current_version

        if (
            knowledge.enabled()
            and resolve_current_version(db, doc)
        ):
            knowledge.enqueue_sync_after_ingest(doc.id, user.id)
            knowflow_synced = True

    invalidate_document_caches(str(user.id))
    message = (
        "已添加到个人级文档库（未分类），正在后台同步知识库索引"
        if knowflow_synced
        else "已添加到个人级文档库（未分类）"
    )
    return {
        "document_id": doc.id,
        "title": doc.title,
        "knowflow_synced": knowflow_synced,
        "message": message,
    }


def generate_report_mindmap(*, question: str, answer: str) -> tuple[str | None, str]:
    """复用知识检索思维导图能力，将报告正文结构化为 Mermaid。"""
    from app.services.knowledge_mindmap_service import build_mindmap_from_answer
    from app.services.knowledge_qa_service import generate_knowledge_mindmap

    mermaid = generate_knowledge_mindmap(question=question, answer=answer)
    if mermaid:
        return mermaid, "llm"
    mermaid = build_mindmap_from_answer(question, answer)
    if mermaid:
        return mermaid, "local"
    return None, "local"


def _gather_report_agentic(
    db: Session,
    user_id: uuid.UUID,
    doc_ids: list[uuid.UUID],
    *,
    message: str,
    topic: str,
    intent: str,
    history: list[AiChatMessage],
    web_on: bool,
    emit: Callable[[dict[str, Any]], None] | None = None,
) -> Any:
    from app.core.async_db import resolve_db_user
    from app.services.knowledge_agentic_service import (
        RESULT_MARKER,
        AgenticReportGatherResult,
        iter_gather_for_report,
    )

    user = resolve_db_user(db, user_id)
    gathered = None
    for item in iter_gather_for_report(
        db,
        user,
        doc_ids,
        message=message,
        topic=topic,
        intent=intent,
        history=history,
        web_enabled=web_on,
        emit=emit,
    ):
        if RESULT_MARKER in item:
            gathered = item[RESULT_MARKER]
    if gathered is None:
        gathered = AgenticReportGatherResult(
            local_hits=[],
            web_items=[],
            doc_titles={},
            plan_reasoning="材料收集未完成，将主要依据模型知识",
            rounds_used=0,
            local_queries=[],
            web_queries=[],
            insufficient_note="未获取到本地或联网材料",
        )
    return gathered


def _gather_report_simple(
    db: Session,
    user_id: uuid.UUID,
    doc_ids: list[uuid.UUID],
    *,
    message: str,
    topic: str,
    intent: str,
    history: list[AiChatMessage],
    web_on: bool,
) -> Any:
    from app.core.async_db import resolve_db_user
    from app.services.knowledge_agentic_service import (
        AgenticReportGatherResult,
        _history_excerpt,
        _plan_report_gathering,
    )
    from app.services.knowledge_agentic_tools import KnowledgeAgenticToolkit
    from app.services.knowledge_qa_service import _doc_titles

    user = resolve_db_user(db, user_id)
    local_queries, web_queries, reasoning = _plan_report_gathering(
        message=message,
        topic=topic,
        intent=intent,
        document_count=len(doc_ids),
        web_allowed=web_on,
        kg_context="",
        history_excerpt=_history_excerpt(history),
    )
    toolkit = KnowledgeAgenticToolkit(
        db,
        user,
        doc_ids,
        web_enabled=web_on,
        include_kg=False,
        retrieve_limit=15,
        web_max_items=10,
    )
    if doc_ids and local_queries:
        for q in local_queries:
            toolkit.retrieve(q, limit=15)
    local_hits = (
        toolkit.accumulated_local_hits
        if toolkit.accumulated_local_hits
        else (
            retrieve_local_hits_for_report(db, user, doc_ids, local_queries)
            if doc_ids and local_queries
            else []
        )
    )
    web_items: list[dict] = []
    if web_on and web_queries:
        for q in web_queries:
            toolkit.web_search(q)
        web_items = toolkit.accumulated_web_items
    return AgenticReportGatherResult(
        local_hits=local_hits,
        web_items=web_items,
        doc_titles=_doc_titles(db, doc_ids) if doc_ids else {},
        plan_reasoning=reasoning,
        rounds_used=1,
        local_queries=local_queries,
        web_queries=web_queries,
    )


def _collect_report_materials(
    db: Session,
    user_id: uuid.UUID,
    doc_ids: list[uuid.UUID],
    *,
    message: str,
    topic: str,
    intent: str,
    history: list[AiChatMessage],
    use_web_search: bool,
    use_agentic: bool,
) -> dict[str, Any]:
    """单次 DB 会话：检查联网配置 + 收集报告材料。"""
    from app.services.knowledge_agentic_service import agentic_enabled

    web_configured = searxng_enabled(db)
    web_on = bool(use_web_search and web_configured)

    if use_agentic and agentic_enabled():
        gathered = _gather_report_agentic(
            db,
            user_id,
            doc_ids,
            message=message,
            topic=topic,
            intent=intent,
            history=history,
            web_on=web_on,
        )
    else:
        gathered = _gather_report_simple(
            db,
            user_id,
            doc_ids,
            message=message,
            topic=topic,
            intent=intent,
            history=history,
            web_on=web_on,
        )
    return {
        "web_on": web_on,
        "gathered": gathered,
    }


async def iter_report_generation_stream(
    *,
    user_id: uuid.UUID,
    message: str,
    history: list[AiChatMessage],
    conversation_id: str | None = None,
    document_ids: list[str] | None = None,
    use_web_search: bool = True,
    use_agentic: bool = True,
) -> AsyncIterator[str]:
    message = message.strip()
    if not message:
        yield json.dumps({"error": "请输入报告需求或补充说明"}, ensure_ascii=False)
        return
    if not is_configured():
        yield json.dumps(
            {"error": "报告生成未配置，请联系管理员配置 DeepSeek API"},
            ensure_ascii=False,
        )
        return

    has_history = _has_prior_assistant_turn(history)
    intent = classify_intent(message, has_history=has_history, history=history)
    topic = resolve_report_topic(message, history)
    yield json.dumps(
        {
            "workflow": {
                "phase": "node_started",
                "title": f"分析意图：{_INTENT_LABELS.get(intent, intent)}",
            }
        },
        ensure_ascii=False,
    )

    local_hits: list[dict] = []
    local_context = ""
    web_context = ""
    all_citations: list[dict] = []
    doc_titles: dict[str, str] = {}
    doc_ids = _parse_document_ids(document_ids)
    from app.core.async_db import run_db_task

    gathered = None
    web_on = False
    from app.services.knowledge_agentic_service import (
        AgenticReportGatherResult,
        agentic_enabled,
    )

    use_agentic_path = bool(use_agentic and agentic_enabled())
    try:
        web_on = await run_db_task(_report_web_on, use_web_search)

        if use_agentic_path:
            loop = asyncio.get_running_loop()
            event_q: asyncio.Queue[Any] = asyncio.Queue()
            gather_holder: dict[str, Any] = {}

            def emit_workflow(ev: dict[str, Any]) -> None:
                loop.call_soon_threadsafe(event_q.put_nowait, ev)

            async def run_agentic_gather() -> None:
                try:
                    gather_holder["gathered"] = await run_db_task(
                        _gather_report_agentic,
                        user_id,
                        doc_ids,
                        message=message,
                        topic=topic,
                        intent=intent,
                        history=history,
                        web_on=web_on,
                        emit=emit_workflow,
                    )
                finally:
                    loop.call_soon_threadsafe(event_q.put_nowait, None)

            gather_task = asyncio.create_task(run_agentic_gather())
            while True:
                item = await event_q.get()
                if item is None:
                    break
                yield json.dumps({"workflow": item}, ensure_ascii=False)
                await asyncio.sleep(0)
            await gather_task
            gathered = gather_holder.get("gathered")
            if gathered is None:
                gathered = AgenticReportGatherResult(
                    local_hits=[],
                    web_items=[],
                    doc_titles={},
                    plan_reasoning="材料收集未完成",
                    rounds_used=0,
                    local_queries=[],
                    web_queries=[],
                    insufficient_note="未获取到材料",
                )
        else:
            yield json.dumps(
                {"workflow": {"phase": "workflow_started", "title": "开始收集报告材料"}},
                ensure_ascii=False,
            )
            await asyncio.sleep(0)
            material = await run_db_task(
                _collect_report_materials,
                user_id,
                doc_ids,
                message=message,
                topic=topic,
                intent=intent,
                history=history,
                use_web_search=use_web_search,
                use_agentic=False,
            )
            web_on = bool(material.get("web_on"))
            gathered = material.get("gathered")
            if gathered is not None:
                if gathered.local_queries:
                    yield json.dumps(
                        {
                            "workflow": {
                                "phase": "node_started",
                                "title": "检索本地资料",
                            }
                        },
                        ensure_ascii=False,
                    )
                    await asyncio.sleep(0)
                if gathered.web_queries:
                    yield json.dumps(
                        {
                            "workflow": {
                                "phase": "node_started",
                                "title": "联网检索相关资料",
                            }
                        },
                        ensure_ascii=False,
                    )
                    await asyncio.sleep(0)
                elif not gathered.local_queries and not gathered.web_queries:
                    yield json.dumps(
                        {
                            "workflow": {
                                "phase": "agent_thought",
                                "title": "无需额外检索",
                                "detail": (gathered.plan_reasoning or "")[:500],
                                "status": "done",
                            }
                        },
                        ensure_ascii=False,
                    )
                    await asyncio.sleep(0)
    except Exception as exc:
        logger.warning("报告材料收集失败: %s", exc, exc_info=True)
        yield json.dumps({"error": "资料检索失败，请稍后重试"}, ensure_ascii=False)
        return

    if gathered is None:
        yield json.dumps({"error": "资料检索失败，请稍后重试"}, ensure_ascii=False)
        return

    local_hits = gathered.local_hits
    web_items = gathered.web_items
    doc_titles = gathered.doc_titles or doc_titles
    insufficient_note = gathered.insufficient_note

    chunk_count = 0
    if local_hits or web_items:
        local_context, web_context, all_citations, chunk_count = (
            build_aligned_report_sources(
                local_hits,
                doc_titles,
                web_items,
                question=f"{topic} {message}".strip(),
            )
        )

    yield json.dumps(
        {"workflow": {"phase": "node_started", "title": "正在整理报告材料"}},
        ensure_ascii=False,
    )
    await asyncio.sleep(0)

    messages = _build_messages(
        message=message,
        history=history,
        intent=intent,
        topic=topic,
        local_context=local_context,
        web_context=web_context,
        web_enabled=web_on,
        local_enabled=bool(doc_ids),
        chunk_count=len(local_hits),
        insufficient_note=insufficient_note,
        local_searched=bool(gathered.local_queries),
        web_searched=bool(gathered.web_queries),
    )

    accumulated = ""
    temperature = 0.35 if intent == "format_adjust" else 0.55
    from app.services.llm_workflow_stream import iter_llm_answer_events

    report_prompt_budget = get_prompt_limits()["report_prompt_max_chars"]
    try:
        async for ev in iter_llm_answer_events(
            messages=messages,
            temperature=temperature,
            think_title="正在撰写报告",
            think_detail="整合材料并生成报告正文…",
            unlimited_output=True,
            max_total_chars=report_prompt_budget,
        ):
            if ev.get("type") == "workflow":
                yield json.dumps({"workflow": ev["data"]}, ensure_ascii=False)
                await asyncio.sleep(0)
            elif ev.get("type") == "delta" and ev.get("text"):
                accumulated += ev["text"]
                yield json.dumps({"delta": ev["text"]}, ensure_ascii=False)
    except httpx.HTTPError as exc:
        logger.warning("报告生成 LLM 流式失败: %s", exc)
        yield json.dumps({"error": "报告生成暂时不可用，请稍后重试"}, ensure_ascii=False)
        return

    reply = accumulated.strip()
    if not reply:
        yield json.dumps({"error": "未能生成报告内容"}, ensure_ascii=False)
        return

    reply, all_citations = finalize_report_citations(reply, all_citations)
    if reply != accumulated.strip():
        yield json.dumps({"replace": reply}, ensure_ascii=False)
    if all_citations:
        yield json.dumps({"citations": all_citations}, ensure_ascii=False)

    out_conv_id = await run_db_task(
        _persist_turn,
        user_id=user_id,
        conversation_id=conversation_id,
        message=message,
        reply=reply,
    )
    yield json.dumps(
        {"workflow": {"phase": "workflow_finished", "title": "完成"}},
        ensure_ascii=False,
    )
    yield json.dumps(
        {
            "done": True,
            "reply": reply,
            "conversation_id": out_conv_id,
            "intent": intent,
            "topic": topic or None,
            "chunks_used": len(local_hits),
            "citations": all_citations,
        },
        ensure_ascii=False,
    )
