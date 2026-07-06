"""知识检索：检索前根据已选文档标题/文件名限定检索范围。"""

from __future__ import annotations

import re
from pathlib import Path

from app.models.document import Document

_QUOTED_PATTERNS = (
    re.compile(r"《([^》]{2,120})》"),
    re.compile(r"「([^」]{2,120})」"),
    re.compile(r'"([^"]{2,120})"'),
    re.compile(r"'([^']{2,120})'"),
)
_FILE_PATTERN = re.compile(
    r"([\w\u4e00-\u9fff][\w\u4e00-\u9fff\-_.]{0,100}"
    r"\.(?:pdf|docx?|xlsx?|pptx?|md|txt|csv|png|jpe?g|webp))",
    re.IGNORECASE,
)
_DOC_REF_PATTERN = re.compile(
    r"([\w\u4e00-\u9fff][\w\u4e00-\u9fff\-_.]{1,80}?)"
    r"(?:这个|这份|该)?(?:文件|文档|报告|材料|附件|资料)",
)
_ASK_PATTERN = re.compile(
    r"^(?:请?(?:帮忙|帮我)?)?(.{2,80}?)"
    r"(?:主要)?(?:讲|说|写|介绍|提到|包含|概述|总结|阐述)(?:了)?"
    r"(?:什么|啥|哪些内容)?[？?]?$",
)
_TOKEN_SPLIT = re.compile(r"[\s，,。.！!？?；;：:\"'《》「」、]+")
_STOP_TOKENS = frozenset(
    {
        "什么",
        "哪些",
        "如何",
        "怎么",
        "怎样",
        "为何",
        "为什么",
        "请问",
        "一下",
        "这个",
        "这份",
        "该",
        "是否",
        "能否",
        "可以",
        "帮忙",
        "帮我",
        "告诉",
        "介绍",
        "说明",
        "总结",
        "概述",
        "内容",
        "主要",
        "关于",
        "里面",
        "其中",
        "文件",
        "文档",
        "报告",
        "材料",
    }
)


def _normalize_name(value: str) -> str:
    text = (value or "").strip().lower()
    if not text:
        return ""
    stem = Path(text).stem if "." in text else text
    return stem.strip()


def _doc_name_labels(title: str, file_name: str) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for raw in (title, file_name, Path(file_name).stem if file_name else ""):
        text = (raw or "").strip()
        if len(text) < 2:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        labels.append(key)
    return labels


def extract_document_name_hints(question: str) -> list[str]:
    """从用户问题中提取明确的文档标题/文件名片段。"""
    q = (question or "").strip()
    if not q:
        return []

    hints: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        text = (raw or "").strip().strip("：:，,。.、")
        if len(text) < 2:
            return
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        hints.append(text)

    for pattern in _QUOTED_PATTERNS:
        for match in pattern.finditer(q):
            add(match.group(1))
    for match in _FILE_PATTERN.finditer(q):
        add(match.group(1))
    for match in _DOC_REF_PATTERN.finditer(q):
        add(match.group(1))
    ask = _ASK_PATTERN.match(q)
    if ask:
        add(ask.group(1))

    return hints


def _extract_search_tokens(question: str) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for raw in _TOKEN_SPLIT.split((question or "").strip()):
        token = raw.strip().lower()
        if len(token) < 2 or token in _STOP_TOKENS or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def score_document_name_match(
    hint: str,
    *,
    title: str,
    file_name: str,
) -> float:
    needle = _normalize_name(hint)
    if len(needle) < 2:
        return 0.0

    best = 0.0
    for candidate in _doc_name_labels(str(title or ""), str(file_name or "")):
        if needle == candidate:
            best = max(best, 1.0)
            continue
        if needle in candidate or candidate in needle:
            best = max(best, 0.88)
            continue
        for suffix in ("报告", "通知", "方案", "制度", "文件", "文档", "说明", "材料"):
            if needle.endswith(suffix):
                stem = needle[: -len(suffix)]
                if stem and (stem in candidate or candidate in stem):
                    best = max(best, 0.82)
    return best


def _question_mentions_doc_name(question_lower: str, labels: list[str]) -> bool:
    for label in sorted(labels, key=len, reverse=True):
        if label in question_lower:
            return True
    return False


def _token_matches_doc_name(token: str, title: str, file_name: str) -> bool:
    needle = token.lower()
    if len(needle) < 2:
        return False
    for label in _doc_name_labels(title, file_name):
        if needle in label:
            return True
    return False


def resolve_retrieval_document_scope(
    docs: list[Document],
    file_names: dict[str, str],
    question: str,
) -> list[Document]:
    """
    检索前限定范围：仅在已选文档中，根据问题与标题/文件名的匹配结果缩小检索对象。
    若无匹配则保持全部已选文档。
    """
    if not docs:
        return docs

    question_lower = (question or "").strip().lower()
    if not question_lower:
        return docs

    matched: list[Document] = []
    seen_ids: set[str] = set()
    hints = extract_document_name_hints(question)
    tokens = _extract_search_tokens(question)

    for doc in docs:
        did = str(doc.id)
        title = str(doc.title or "").strip()
        file_name = str(file_names.get(did) or "").strip()
        labels = _doc_name_labels(title, file_name)

        if labels and _question_mentions_doc_name(question_lower, labels):
            seen_ids.add(did)
            matched.append(doc)
            continue

        if hints and any(
            score_document_name_match(h, title=title, file_name=file_name) >= 0.75
            for h in hints
        ):
            seen_ids.add(did)
            matched.append(doc)

    for token in tokens:
        for doc in docs:
            did = str(doc.id)
            if did in seen_ids:
                continue
            title = str(doc.title or "").strip()
            file_name = str(file_names.get(did) or "").strip()
            if _token_matches_doc_name(token, title, file_name):
                seen_ids.add(did)
                matched.append(doc)

    return matched if matched else docs


def match_documents_by_name_hints(
    docs: list[Document],
    file_names: dict[str, str],
    hints: list[str],
    *,
    min_score: float = 0.75,
) -> list[Document]:
    if not docs or not hints:
        return []

    scored: list[tuple[float, Document]] = []
    for doc in docs:
        did = str(doc.id)
        file_name = str(file_names.get(did, "") or "")
        title = str(doc.title or "")
        best = max(
            (score_document_name_match(h, title=title, file_name=file_name) for h in hints),
            default=0.0,
        )
        if best >= min_score:
            scored.append((best, doc))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [doc for _, doc in scored]


def match_documents_for_question(
    docs: list[Document],
    file_names: dict[str, str],
    question: str,
    *,
    min_score: float = 0.75,
) -> list[Document]:
    """兼容旧调用：等价于 resolve_retrieval_document_scope。"""
    _ = min_score
    return resolve_retrieval_document_scope(docs, file_names, question)
