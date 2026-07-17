"""报告生成 — 检索、材料收集、流式撰写与导出。"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.chat_context import trim_chat_history
from app.core.platform_assistant import assistant_report_persona
from app.core.prompt_budget import (
    fit_messages_to_total_budget,
    get_prompt_limits,
    truncate_to_budget,
)
from app.core.report_skill_catalog import (
    REPORT_MIN_CHARS,
    REPORT_TARGET_CHARS,
    report_writing_quality_instruction,
)
from app.integrations.deepseek_client import is_configured
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
_PER_QUERY_LOCAL_HITS = 20
_MAX_LOCAL_CHUNKS = 40
_MAX_CHARS_PER_CHUNK = 2400
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

_WEB_NEWS_QUERY_SUFFIXES = (
    "最新动态",
    "近期新闻",
    "最新政策",
)

_MAX_HISTORY = 16

_REPORT_SYSTEM = f"""{assistant_report_persona()}。你的任务不是像问答助手那样给出简短归纳，而是撰写一份内容充实的长报告。

与「知识检索问答」的本质区别：
- 知识检索：用少量片段做归纳总结，回答要精炼
- 报告生成：从材料中大量取材，改写、扩写、重组后写入报告正文，篇幅应明显长于材料摘要

写作原则：
1. **大量取材**：下方编号材料块是已召回的原文，应尽可能多地被吸收进报告各章节
2. **扩写整合**：在忠实于材料含义的前提下解释、展开与衔接；不得编造材料中不存在的数据、文号或结论
3. **结构化长文**：使用 Markdown 标题；按报告类型 Skill 模板与 outline 组织章节；章节之间须有清晰逻辑递进，避免并列堆砌
4. **深度论证**：关键判断须给出依据与推理过程，多角度交叉分析后形成综合结论，禁止浅层罗列与空话套话
5. **引用编号（极其重要）**：
   - 仅能在句末用 [1]、[2] 标注；编号必须与下方材料块 [n] **严格一一对应**
   - 界面底部会展示材料来源；请在引用材料的句末尽量标注 [n]
6. **禁止来源叙述**：正文不得出现文档名、URL、「参考来源」「参考文献」等章节
7. **信息源优先级（冲突时必须遵守）**：
   - **优先级 1 · 本地知识库** > **优先级 2 · 联网检索** > **优先级 3 · 模型知识**
8. **不足即说明**：材料不够时标注「待补充」，勿虚构
9. **语言风格**：专业自然的中文研究报告写法，避免 AI 套话与翻译腔
10. **Mermaid 图表（须可解析）**：
   - 围栏内第一行必须是 `flowchart TD`、`mindmap`、`sequenceDiagram` 等合法类型声明
   - 节点 ID 仅用英文字母数字（如 A、B1、step1）；**中文标签写在方括号内并加英文双引号**
   - 示例：`flowchart TD` 下写 `A["虚拟电厂"] --> B["云平台架构"]`，禁止 `虚拟电厂 --> 云平台`
   - mindmap 用缩进表示层级，节点文字直接写中文，不要用引号包裹；根节点形如 root((主题))
11. **直入正文**：禁止输出开场白、任务复述、写作计划或对用户指令的回应（如「好的，遵照您的指示…」「我将以小析的身份…」）；输出必须从 `# 报告标题` 或第一个章节标题直接开始
12. **大批量复用材料**：下方编号材料块应大比例被吸收进各章节；每个二级及以下小标题至少整合 2–3 段不同材料的表述、数据或案例，避免只摘一两句

禁止：在正文中输出工具调用、DSML 标记或任何非报告正文内容。"""

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

_REPORT_TEMPLATE_INSTRUCTION = """用户上传了已有的报告或模板作为参考，请严格遵循其结构、章节设置和写作风格，
根据用户当前需求生成新的报告内容。

参考模板使用规则：
1. **结构遵循**：保持与模板一致的章节层次、标题风格和逻辑结构，不要擅自增减或调整章节顺序
2. **内容填充**：对模板中的具体内容（如数据、案例、分析、政策等），根据下方编号材料进行填充和完善；材料不足处在相应章节标注「待补充」
3. **占位符处理**：若模板中含有占位符（如「{}」「待填写」「xxx」等），应替换为实际内容或根据上下文补充
4. **沿用与升级**：模板中已有的实质性分析、判断和结论，可以在新报告中沿用或改写升级
5. **格式一致**：保持与模板一致的格式风格（表格、列表、引用格式等）
6. **不复制无效内容**：不要直接复制模板中的示例性/占位性文字到新报告正文中

模板内容位于下方【上传的参考模板/报告】区域。"""

REPORT_OPTIMIZE_PRESETS: dict[str, dict[str, str]] = {
    "expand": {
        "label": "扩写充实",
        "description": "补充细节、论据与背景分析",
        "prompt": "请在当前报告基础上扩写：补充背景说明、论据、对比分析与细节，"
        f"全文尽量达到 {REPORT_MIN_CHARS} 字以上。"
        "保持原有章节结构与引用编号 [n] 不变；新增内容需标注出处，材料冲突时按本地知识库 > 联网检索 > 模型知识优先级处理。",
    },
    "shorten": {
        "label": "精简压缩",
        "description": "删繁就简，保留核心结论与关键数据",
        "prompt": "请精简当前报告篇幅：保留核心论点、关键数据与结论建议，删除重复表述与次要细节，不改变既有引用编号含义。",
    },
    "add_cases": {
        "label": "补充案例",
        "description": "增加典型实践案例与应用场景",
        "prompt": "请在报告中补充 2–3 个典型实践或应用场景案例，与正文分析相呼应，句末用 [n] 标注出处。",
    },
    "executive_summary": {
        "label": "执行摘要",
        "description": "在文首增加 Executive Summary",
        "prompt": "请在报告文首增加 Executive Summary（约 200 字），概括研究背景、主要发现与核心建议，不重复正文细节。",
    },
    "table_format": {
        "label": "表格呈现",
        "description": "将适合对比的内容改为表格",
        "prompt": "请将报告中适合横向对比的内容（如指标、方案、框架差异）改为 Markdown 表格呈现，其余章节结构与表述保持不变。",
    },
    "formal_polish": {
        "label": "正式润色",
        "description": "优化表述，更正式连贯",
        "prompt": "请润色全文表述：使语气更正式、段落衔接更连贯，不改变事实与引用编号含义；"
        "去除 AI 套话（如「综上所述」「总结如下」）与英译中腔调，保持自然中文报告语感。",
    },
    "add_recommendations": {
        "label": "强化建议",
        "description": "扩展结论与可落地行动建议",
        "prompt": "请扩展「结论与建议」章节：在现有结论基础上补充可落地的行动建议、实施路径与主要风险提示。",
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
    """联网检索查询：首次生成时侧重最新新闻与政策动态。"""
    base = topic or extract_report_topic(message) or message.strip()
    queries: list[str] = []
    if base:
        queries.append(base)
    if intent == "initial" and base:
        for suffix in _WEB_NEWS_QUERY_SUFFIXES:
            queries.append(f"{base} {suffix}")
    elif intent == "follow_up":
        current = message.strip()[:120]
        if current and current != base:
            queries.append(current)
        if base and re.search(r"最新|近期|新闻|动态|政策", message):
            queries.append(f"{base} 最新动态")
    seen: set[str] = set()
    ordered: list[str] = []
    for q in queries:
        key = q.lower()
        if key and key not in seen:
            seen.add(key)
            ordered.append(q)
    return ordered[:4]


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
    return ordered[:8]


def ensure_report_scoped_local_queries(
    *,
    message: str,
    topic: str,
    intent: str,
    document_count: int,
    planned_queries: list[str],
    history: list[AiChatMessage] | None = None,
    max_queries: int = 6,
) -> list[str]:
    """用户勾选文档时，必须在所选文档范围内检索（格式调整除外）。"""
    if document_count <= 0 or intent == "format_adjust":
        return list(planned_queries)
    scoped = build_local_retrieval_queries(
        message, topic=topic, intent=intent, history=history
    )
    merged: list[str] = []
    seen: set[str] = set()
    for q in planned_queries + scoped:
        text = (q or "").strip()
        key = text.lower()
        if key and key not in seen:
            seen.add(key)
            merged.append(text)
    return merged[:max_queries]


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

    hits = retrieve_merged_hits_for_queries(
        db,
        user,
        doc_ids,
        queries,
        limit_per_query=_PER_QUERY_LOCAL_HITS,
        merge_nearby=False,
        max_total=_MAX_LOCAL_CHUNKS,
        narrow_by_name=False,
    )
    return _boost_report_local_fulltext(db, user, doc_ids, queries, hits)


def _boost_report_local_fulltext(
    db: Session,
    user: User,
    doc_ids: list[uuid.UUID],
    queries: list[str],
    hits: list[dict],
) -> list[dict]:
    """KnowFlow/PageIndex 无命中时，对已选文档做本地全文兜底（含未同步索引的已上传文件）。"""
    if not doc_ids or not queries:
        return hits
    from app.core.permissions import PermissionLevel
    from app.services.compare_service import validate_document_scope
    from app.services.knowledge_qa.retrieval import _local_retrieve

    try:
        docs = validate_document_scope(
            db,
            user,
            doc_ids,
            min_count=1,
            max_count=20,
            required_level=PermissionLevel.query.value,
            allow_index_only=True,
            omit_unready=len(doc_ids) > 1,
        )
    except Exception:
        logger.warning("报告本地全文兜底：validate_document_scope 失败", exc_info=True)
        return hits
    if not docs:
        return hits

    extra: list[dict] = []
    for q in queries:
        q = (q or "").strip()
        if not q:
            continue
        extra.extend(
            _local_retrieve(db, user, docs, doc_ids, q, limit=_PER_QUERY_LOCAL_HITS)
        )
    if not extra:
        return hits
    return merge_retrieval_hits(hits + extra, max_total=_MAX_LOCAL_CHUNKS)


def summarize_report_doc_selection(
    db: Session,
    user: User,
    doc_ids: list[uuid.UUID],
) -> dict[str, Any]:
    """报告页已选文档的可检索性摘要（用于 workflow 提示）。"""
    from app.services.document_index_service import (
        enrich_document_index_meta,
        is_index_ready_meta,
    )
    from app.services.document_service import get_document, resolve_current_version

    total = len(doc_ids)
    has_file = 0
    index_ready = 0
    knowledge_synced = 0
    unready_titles: list[str] = []

    for did in doc_ids:
        doc = get_document(db, did)
        if not doc or doc.deleted_at:
            continue
        if resolve_current_version(db, doc, repair=True):
            has_file += 1
        meta = enrich_document_index_meta(db, user, [doc], live_ragflow=False).get(
            str(did), {}
        )
        if is_index_ready_meta(meta):
            index_ready += 1
        if meta.get("knowledge_synced"):
            knowledge_synced += 1
        if not is_index_ready_meta(meta):
            unready_titles.append((doc.title or "未命名文档").strip() or str(did))

    return {
        "total": total,
        "has_file": has_file,
        "index_ready": index_ready,
        "knowledge_synced": knowledge_synced,
        "unready_titles": unready_titles[:5],
    }


def build_report_local_miss_detail(
    summary: dict[str, Any],
    *,
    local_hit_count: int,
) -> str:
    if local_hit_count > 0:
        return ""
    total = int(summary.get("total") or 0)
    if total <= 0:
        return ""
    index_ready = int(summary.get("index_ready") or 0)
    has_file = int(summary.get("has_file") or 0)
    synced = int(summary.get("knowledge_synced") or 0)
    unready = list(summary.get("unready_titles") or [])

    if index_ready == 0 and has_file == 0:
        return (
            f"已选 {total} 份文档，但均未检测到可读取的文件版本。"
            "请确认文档已在「文档库」上传成功。"
        )
    if index_ready == 0:
        hint = (
            f"已选 {total} 份文档，知识库索引均未完成（0/{total}）。"
            "左侧树中文档需显示为已索引；请在「文档库」等待同步/解析完成（状态「已完成」）后再生成报告。"
        )
        if unready:
            hint += f"（如：{'、'.join(unready[:3])}{'…' if len(unready) > 3 else ''}）"
        return hint
    if synced < index_ready:
        return (
            f"已选 {total} 份，{index_ready} 份已索引，但检索未命中相关内容。"
            "可尝试换用更贴近文档标题的关键词，或检查文档是否为扫描件/OCR 质量过低。"
        )
    return (
        f"已在 {index_ready} 份已索引文档中检索，未命中与主题相关的片段。"
        "请确认左侧勾选的是包含目标内容的文档，或补充更具体的报告主题。"
    )


def _summarize_report_doc_selection_task(
    db: Session,
    user_id: uuid.UUID,
    doc_ids: list[uuid.UUID],
) -> dict[str, Any]:
    from app.core.async_db import resolve_db_user

    user = resolve_db_user(db, user_id)
    return summarize_report_doc_selection(db, user, doc_ids)


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


def _format_web_context(items: list[dict], *, start_index: int, verification: dict | list | None = None) -> str:
    if not items:
        return ""
    blocks: list[str] = []
    for i, row in enumerate(items, start=start_index):
        # 优先使用全文，次选摘要
        snippet = (row.get("full_text") or row.get("snippet") or "").strip()
        if row.get("full_text"):
            # 全文过长时截取前 3000 字
            full = row["full_text"]
            snippet = full[:3000]
            if len(full) > 3000:
                snippet += "\n…（以下省略）"
            snippet += f"\n（来源：{row.get('title', '')} — 共约 {len(full)} 字）"
        elif snippet:
            pass
        else:
            continue
        blocks.append(f"[{i}]\n{snippet}")

    # 交叉验证摘要
    if verification:
        import re
        if isinstance(verification, dict):
            vlist = list(verification.values()) if verification else []
        elif isinstance(verification, list):
            vlist = verification
        else:
            vlist = []
        vblocks = ["\n\n## 跨源交叉验证"]
        for v in vlist[:8]:
            if not isinstance(v, dict):
                continue
            claim = (v.get("claim") or "")[:120]
            consistent = v.get("consistent", True)
            sources = v.get("sources") or []
            value_count = v.get("value_count", 0)
            if consistent and value_count <= 1:
                vblocks.append(f"- ✅ {claim}")
            elif consistent:
                vblocks.append(f"- ✅ {claim}（多源一致）")
            else:
                numbers = re.findall(r"\d+[\.\d]*(?:万|亿|%|倍)?", claim)
                if numbers:
                    vblocks.append(f"- ⚠️ {claim}（数值不一致，请核实）")
                else:
                    vblocks.append(f"- ℹ️ {claim}（{len(sources)} 个来源提及）")
        if len(vblocks) > 1:
            blocks.extend(vblocks)

    return "\n\n".join(blocks)


def build_web_citations(items: list[dict], *, start_index: int = 1) -> list[dict]:
    citations: list[dict] = []
    for i, row in enumerate(items, start=start_index):
        snippet = (row.get("full_text") or row.get("snippet") or "")[:2000]
        citations.append(
            {
                "index": i,
                "title": (row.get("title") or "网页").strip(),
                "snippet": snippet,
                "url": (row.get("url") or "").strip() or None,
                "source": "web",
                "document_id": None,
                "preview_available": False,
            }
        )
    return citations


def _intent_instruction(intent: str, *, chunk_count: int) -> str:
    if intent == "format_adjust":
        return (
            "用户希望调整已有报告的格式或结构。请主要依据对话中的上一版报告内容进行重写，"
            "除非用户明确要求补充新信息。"
        )
    if intent == "follow_up":
        return (
            "用户在已有报告基础上追问或要求补充。请结合对话历史中的上一版完整报告正文、"
            "用户本轮输入与下方新检索材料，输出**完整修订后的报告**（不是只回复差异段落）。"
            "对新增或修订内容在句末标注 [n]；冲突时本地知识库 > 联网检索 > 模型知识。"
        )
    material_hint = (
        f"已从本地知识库召回 {chunk_count} 段原文片段，请尽量让**多数片段**在正文中得到体现；"
        "对每个二级/三级小标题，从材料中选取并改写整合多段原文，避免浅尝辄止；"
        "与联网或模型知识冲突时以本地片段为准。"
        if chunk_count
        else "本次未选本地文档或未命中片段，请主要依据联网材料撰写；"
        "联网与模型知识冲突时以联网为准；模型知识仅作空白补全。"
    )
    return (
        "用户希望生成一份新的研究报告。请输出完整、篇幅充足的长报告，"
        f"首轮正文不少于 {REPORT_MIN_CHARS} 字、尽量达到 {REPORT_TARGET_CHARS} 字；"
        "各章节逻辑递进、论证有深度、多角度互证；"
        "每个小标题下须有充分段落展开，禁止标题下仅一两句话。"
        f"{material_hint}"
    )


def _report_skill_system_block(
    db: Session,
    user: User,
    skill_name: str,
) -> str:
    """将报告类型 Skill 模板注入 system，无需 tool_calls。"""
    name = (skill_name or "").strip()
    if not name:
        return ""
    from app.services.agent_tools import build_skill_md_context_block, fetch_uploaded_skill_md

    skill_md = fetch_uploaded_skill_md(db, name, user=user)
    block = build_skill_md_context_block(name, skill_md or "", has_script=False)
    parts = [p for p in [block, report_writing_quality_instruction(name)] if p]
    return "\n\n".join(parts)


def _build_messages(
    *,
    db: Session,
    user: User,
    message: str,
    history: list[AiChatMessage],
    intent: str,
    topic: str,
    skill_name: str,
    local_context: str,
    web_context: str,
    web_enabled: bool,
    local_enabled: bool,
    chunk_count: int,
    insufficient_note: str | None = None,
    local_searched: bool = False,
    web_searched: bool = False,
    attachment_context: str | None = None,
) -> list[dict]:
    limits = get_prompt_limits()
    local_context = truncate_to_budget(
        local_context, limits["report_context_max_chars"] // 2
    )
    web_context = truncate_to_budget(web_context, limits["report_context_max_chars"] // 2)
    message = truncate_to_budget(message.strip(), limits["user_max_chars"])

    parts = [_REPORT_SYSTEM, _intent_instruction(intent, chunk_count=chunk_count)]
    skill_block = _report_skill_system_block(db, user, skill_name)
    if skill_block:
        parts.append(skill_block)
    if insufficient_note:
        parts.append(
            "【材料不足】当前召回材料可能不足以完整撰写报告。"
            f"不足方面：{insufficient_note}。"
            "请基于已有编号材料尽力撰写；对缺失部分在相应章节标注「待补充」，"
            "不要编造缺失的具体数据或政策文号。"
        )
    if topic:
        parts.append(f"报告主题：{topic}")
    if attachment_context:
        parts.append(attachment_context)
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
    tail = trim_chat_history(history, max_messages=_MAX_HISTORY)
    for item in tail:
        messages.append({"role": item.role, "content": item.content.strip()})
    messages.append({"role": "user", "content": message})
    return fit_messages_to_total_budget(messages, limits["report_prompt_max_chars"])


def _report_web_on(db: Session, use_web_search: bool) -> bool:
    return bool(use_web_search and searxng_enabled(db))


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

    user = resolve_db_user(db, user_id)

    # 加载知识图谱上下文（多跳推理），供规划器感知实体关系链
    kg_ctx_data = None
    if doc_ids:
        from app.core.permissions import user_has_permission
        from app.services.kg_service import retrieve_kg_context_for_question

        if user_has_permission(db, user, "feature.kg"):
            try:
                kg_ctx_data = retrieve_kg_context_for_question(
                    db, user, f"{topic} {message}".strip()
                )
            except Exception:
                logger.warning("报告材料收集：知识图谱上下文检索失败", exc_info=True)
    kg_plan_text = kg_ctx_data.context_text if kg_ctx_data else ""

    local_queries, web_queries, reasoning = _plan_report_gathering(
        message=message,
        topic=topic,
        intent=intent,
        document_count=len(doc_ids),
        web_allowed=web_on,
        kg_context=kg_plan_text,
        history_excerpt=_history_excerpt(history),
        history=history,
    )
    toolkit = KnowledgeAgenticToolkit(
        db,
        user,
        doc_ids,
        web_enabled=web_on,
        include_kg=False,
        retrieve_limit=15,
        web_max_items=10,
        narrow_by_name=False,
    )
    if doc_ids and local_queries:
        toolkit.retrieve_many(local_queries, limit=15)
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
    if web_on and topic:
        # 统一走 deep_research 子智能体进行联网调研，替代逐条 web_search 调用
        toolkit.deep_research(f"{topic} {message}".strip())
        web_items = toolkit.accumulated_web_items
    from app.services.knowledge_qa_service import _doc_titles

    return AgenticReportGatherResult(
        local_hits=local_hits,
        web_items=web_items,
        doc_titles=_doc_titles(db, doc_ids) if doc_ids else {},
        plan_reasoning=reasoning,
        rounds_used=1,
        local_queries=local_queries,
        web_queries=web_queries,
        kg_ctx=kg_ctx_data,
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
    return {"web_on": web_on, "gathered": gathered}


async def iter_report_generation_stream(
    *,
    user_id: uuid.UUID,
    message: str,
    history: list[AiChatMessage],
    conversation_id: str | None = None,
    document_ids: list[str] | None = None,
    use_web_search: bool = True,
    use_agentic: bool = True,
    attachment_session_id: str | None = None,
) -> AsyncIterator[str]:
    """报告生成 SSE：确定性材料收集 + 纯撰写流式 LLM（无 tool_calls）。"""
    import json

    from app.core.async_db import run_db_task
    from app.services.report_agent_skills import (
        build_report_workflow_intent_title,
        is_report_page_message_acceptable,
        report_skill_label,
        resolve_report_skill_for_turn,
    )

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
    if not is_report_page_message_acceptable(message, has_history=has_history):
        from app.services.report_generation_agent_service import (
            _iter_report_input_hint_payloads,
        )

        for payload in _iter_report_input_hint_payloads():
            yield payload
        return

    intent = classify_intent(message, has_history=has_history, history=history)
    topic = resolve_report_topic(message, history)
    doc_ids = _parse_document_ids(document_ids)

    from app.database import SessionLocal
    from app.services.agent_profile_service import resolve_agent_skill_names

    db_boot = SessionLocal()
    try:
        from app.core.async_db import resolve_db_user

        resolve_db_user(db_boot, user_id)
        available_skills = set(resolve_agent_skill_names(db_boot, "report"))
        skill_name = resolve_report_skill_for_turn(message, history, available_skills)
        if skill_name not in available_skills:
            from app.services.report_agent_skills import pick_available_report_skill

            skill_name = pick_available_report_skill(message, available_skills) or skill_name
    finally:
        db_boot.close()

    intent_title = build_report_workflow_intent_title(
        skill_name=skill_name,
        revision_intent=intent,
        has_history=has_history,
    )
    yield json.dumps(
        {"workflow": {"phase": "node_started", "title": f"分析意图：{intent_title}"}},
        ensure_ascii=False,
    )
    await asyncio.sleep(0)

    from app.services.knowledge_agentic_service import (
        AgenticReportGatherResult,
        agentic_enabled,
    )

    gathered: AgenticReportGatherResult | None = None
    web_on = False
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
                wf = dict(item)
                wf.setdefault("agent_id", "report")
                wf.setdefault("agent_title", "撰写报告")
                yield json.dumps({"workflow": wf}, ensure_ascii=False)
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
    except Exception as exc:
        logger.warning("报告材料收集失败: %s", exc, exc_info=True)
        yield json.dumps({"error": "资料检索失败，请稍后重试"}, ensure_ascii=False)
        return

    if gathered is None:
        yield json.dumps({"error": "资料检索失败，请稍后重试"}, ensure_ascii=False)
        return

    local_hits = gathered.local_hits
    web_items = gathered.web_items
    doc_titles = gathered.doc_titles or {}
    insufficient_note = gathered.insufficient_note

    if doc_ids:
        doc_summary = await run_db_task(
            _summarize_report_doc_selection_task, user_id, doc_ids
        )
        miss_detail = build_report_local_miss_detail(
            doc_summary, local_hit_count=len(local_hits)
        )
        if miss_detail:
            yield json.dumps(
                {
                    "workflow": {
                        "phase": "agent_thought",
                        "title": "本地文档检索未命中",
                        "detail": miss_detail,
                        "tool": "knowledge_retrieve",
                        "status": "done",
                    }
                },
                ensure_ascii=False,
            )
            await asyncio.sleep(0)
            if not insufficient_note:
                insufficient_note = miss_detail
        elif doc_summary.get("index_ready", 0) > 0:
            yield json.dumps(
                {
                    "workflow": {
                        "phase": "agent_thought",
                        "title": "本地文档检索完成",
                        "detail": (
                            f"已索引 {doc_summary['index_ready']}/{doc_summary['total']} 份，"
                            f"命中 {len(local_hits)} 段材料"
                        ),
                        "tool": "knowledge_retrieve",
                        "status": "done",
                    }
                },
                ensure_ascii=False,
            )
            await asyncio.sleep(0)

    local_context = ""
    web_context = ""
    all_citations: list[dict] = []
    if local_hits or web_items:
        local_context, web_context, all_citations, _ = build_aligned_report_sources(
            local_hits,
            doc_titles,
            web_items,
            question=f"{topic} {message}".strip(),
        )

    # 合并知识图谱上下文（多跳推理结果），图谱优先于文档库编号
    if gathered.kg_ctx is not None:
        from app.services.kg_service import merge_kg_qa_into_context

        # merge_kg_qa_into_context 返回单字符串，不可解包
        local_context = merge_kg_qa_into_context(
            None, None, gathered.kg_ctx, base_context=local_context
        )

    yield json.dumps(
        {"workflow": {"phase": "node_started", "title": "正在整理报告材料"}},
        ensure_ascii=False,
    )
    await asyncio.sleep(0)

    # 加载附件模板（用户上传的已有报告/模板）
    attachment_context: str | None = None
    if attachment_session_id:
        yield json.dumps(
            {
                "workflow": {
                    "phase": "node_started",
                    "title": "加载参考模板",
                    "detail": "正在读取用户上传的已有报告/模板…",
                }
            },
            ensure_ascii=False,
        )
        await asyncio.sleep(0)
        try:
            from app.core.text_utils import truncate_text
            from app.services.ai_chat_attachment_service import (
                get_owned_session,
            )

            manifest = get_owned_session(user_id, attachment_session_id)
            files = manifest.get("files") or []
            usable = [f for f in files if isinstance(f, dict)]
            if usable:
                template_parts: list[str] = []
                for idx, item in enumerate(usable, 1):
                    title = str(item.get("file_name") or f"附件{idx}")
                    text = truncate_text(str(item.get("full_text") or ""), 6000)
                    warning = (item.get("warning") or "").strip()
                    template_parts.append(f"### 模板 {idx}: {title}")
                    if warning:
                        template_parts.append(f"（提取说明: {warning}）")
                    template_parts.append(text or "（未能提取正文）")
                    template_parts.append("")
                body = "\n".join(template_parts).strip()
                if body:
                    attachment_context = (
                        _REPORT_TEMPLATE_INSTRUCTION
                        + "\n\n【上传的参考模板/报告】\n"
                        + body
                    )
                    yield json.dumps(
                        {
                            "workflow": {
                                "phase": "agent_thought",
                                "title": "参考模板已加载",
                                "detail": f"已读取 {len(usable)} 个文件作为报告参考模板",
                                "tool": "attachment_load",
                                "status": "done",
                            }
                        },
                        ensure_ascii=False,
                    )
                else:
                    yield json.dumps(
                        {
                            "workflow": {
                                "phase": "agent_thought",
                                "title": "附件内容为空",
                                "detail": "无法从上传的文件中提取正文内容",
                                "tool": "attachment_load",
                                "status": "done",
                            }
                        },
                        ensure_ascii=False,
                    )
        except Exception:
            logger.warning("报告生成加载附件模板失败", exc_info=True)
            yield json.dumps(
                {
                    "workflow": {
                        "phase": "agent_thought",
                        "title": "附件模板加载失败",
                        "detail": "已上传的参考模板读取失败，将继续使用其他材料生成",
                        "tool": "attachment_load",
                        "status": "done",
                    }
                },
                ensure_ascii=False,
            )

    db = SessionLocal()
    try:
        from app.core.async_db import resolve_db_user

        user = resolve_db_user(db, user_id)

        messages = _build_messages(
            db=db,
            user=user,
            message=message,
            history=history,
            intent=intent,
            topic=topic,
            skill_name=skill_name,
            local_context=local_context,
            web_context=web_context,
            web_enabled=web_on,
            local_enabled=bool(doc_ids),
            chunk_count=len(local_hits),
            insufficient_note=insufficient_note,
            local_searched=bool(gathered.local_queries),
            web_searched=bool(gathered.web_queries),
            attachment_context=attachment_context,
        )
    finally:
        db.close()

    accumulated = ""
    temperature = 0.35 if intent == "format_adjust" else 0.55
    limits = get_prompt_limits()
    from app.services.llm_workflow_stream import iter_llm_answer_events

    try:
        async for ev in iter_llm_answer_events(
            messages=messages,
            temperature=temperature,
            think_title="正在撰写报告",
            think_detail="按模板整合多源材料，逐章充实扩写…",
            unlimited_output=True,
            max_total_chars=limits["report_prompt_max_chars"],
        ):
            if ev.get("type") == "workflow":
                data = dict(ev["data"] or {})
                data.setdefault("agent_id", "report")
                data.setdefault("agent_title", "撰写报告")
                yield json.dumps({"workflow": data}, ensure_ascii=False)
                await asyncio.sleep(0)
            elif ev.get("type") == "error":
                yield json.dumps(
                    {"error": ev.get("message") or "报告生成暂时不可用，请稍后重试"},
                    ensure_ascii=False,
                )
                return
            elif ev.get("type") == "delta" and ev.get("text"):
                accumulated += ev["text"]
                yield json.dumps({"delta": ev["text"]}, ensure_ascii=False)
    except httpx.HTTPError as exc:
        logger.warning("报告生成 LLM 流式失败: %s", exc)
        yield json.dumps({"error": "报告生成暂时不可用，请稍后重试"}, ensure_ascii=False)
        return
    except Exception as exc:
        logger.warning("报告生成 LLM 阶段异常: %s", exc, exc_info=True)
        yield json.dumps({"error": "报告生成暂时不可用，请稍后重试"}, ensure_ascii=False)
        return

    reply = accumulated.strip()
    if not reply:
        yield json.dumps(
            {"error": "未能生成报告内容，请检查语言模型配置与账户状态后重试"},
            ensure_ascii=False,
        )
        return

    from app.core.report_mermaid_sanitize import sanitize_report_markdown_mermaid
    from app.integrations.markdown_docx_export import strip_report_generation_preamble

    reply = sanitize_report_markdown_mermaid(reply)
    reply = strip_report_generation_preamble(reply)
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
            "report_skill": skill_name,
            "report_skill_label": report_skill_label(skill_name),
            "topic": topic or None,
            "chunks_used": len(local_hits),
            "citations": all_citations,
        },
        ensure_ascii=False,
    )


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
        prepare_report_markdown_for_export,
    )
    from app.services.document_service import create_document, create_initial_uploaded_version

    safe_title = (title or "研究报告").strip()[:500] or "研究报告"
    export_markdown = prepare_report_markdown_for_export(markdown)
    try:
        content = markdown_to_docx_bytes(
            title=safe_title,
            markdown_text=export_markdown,
            for_export=False,
        )
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


def list_report_agent_skills(db: Session, user: User) -> list[dict[str, str]]:
    """报告撰写智能体当前挂载的报告类型 Skill（供功能页快捷入口）。"""
    from app.core.report_skill_catalog import (
        REPORT_SKILL_LABELS,
        REPORT_SKILL_NAMES,
        REPORT_SKILL_SAMPLE_PROMPTS,
    )
    from app.services.agent_profile_service import resolve_agent_skill_names
    from app.services.skill_chat_service import get_user_skill_catalog

    allowed = set(resolve_agent_skill_names(db, "report"))
    catalog = {item.name: item for item in get_user_skill_catalog(db, user)}
    out: list[dict[str, str]] = []
    for name in REPORT_SKILL_NAMES:
        if name not in allowed:
            continue
        item = catalog.get(name)
        title = REPORT_SKILL_LABELS.get(name, name)
        description = (item.description if item else "") or ""
        out.append(
            {
                "name": name,
                "title": title,
                "description": description,
                "sample_prompt": REPORT_SKILL_SAMPLE_PROMPTS.get(
                    name, f"撰写一份{title}，主题是"
                ),
            }
        )
    return out


__all__ = [
    "REPORT_OPTIMIZE_PRESETS",
    "build_aligned_report_sources",
    "build_local_retrieval_queries",
    "build_report_context_block",
    "build_search_queries",
    "build_web_citations",
    "classify_intent",
    "extract_report_topic",
    "finalize_report_citations",
    "generate_report_mindmap",
    "get_meta",
    "import_report_to_library",
    "iter_report_generation_stream",
    "list_optimize_presets",
    "merge_retrieval_hits",
    "resolve_report_topic",
    "retrieve_local_hits_for_report",
]
