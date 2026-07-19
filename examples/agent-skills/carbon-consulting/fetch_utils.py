"""网页 HTML 内存分析 — 多站点智能解析，只产出摘要，不持久化原文。"""
from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser

_MAX_SNIPPET = 800
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_SKIP_TAGS = frozenset({"script", "style", "noscript", "nav", "footer", "header"})


class _HtmlAnalyzer(HTMLParser):
    """轻量 HTML 分析（纯 stdlib，无需 bs4/lxml）。"""
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.headings: list[str] = []
        self._body_parts: list[str] = []
        self._tag_stack: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._in_article = False
        self._article_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        self._tag_stack.append(t)
        if t == "title":
            self._in_title = True
        if t in _SKIP_TAGS:
            self._skip_depth += 1
        # 尝试识别主要正文区域
        if t in ("article", "main") or any(
            k.lower() in ("id", "class")
            and v
            and any(kw in v.lower() for kw in ("content", "article", "main", "detail", "news"))
            for k, v in attrs
        ):
            self._in_article = True
            self._article_depth = len(self._tag_stack)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if self._tag_stack and self._tag_stack[-1] == t:
            self._tag_stack.pop()
        if t == "title":
            self._in_title = False
        if t in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        # 退出正文区域
        if self._in_article and len(self._tag_stack) < self._article_depth:
            self._in_article = False

    def handle_data(self, data: str) -> None:
        text = _clean(data)
        if not text:
            return
        if self._in_title:
            self.title += text
        elif self._skip_depth == 0:
            tag = self._tag_stack[-1] if self._tag_stack else ""
            if tag in _HEADING_TAGS:
                if text not in self.headings:
                    self.headings.append(text)
            else:
                self._body_parts.append(text)


def _clean(text: str) -> str:
    return unescape(re.sub(r"\s+", " ", (text or ""))).strip()


def _extract_price_data(text: str) -> list[str]:
    """从文本中提取碳价相关的数据行。"""
    lines = []
    for line in text.split("。"):
        line = line.strip()
        if not line:
            continue
        # 价格相关关键词
        price_kw = (
            "碳价", "成交价", "均价", "收盘价", "开盘价", "最高价", "最低价",
            "成交量", "成交额", "交易量", "交易额", "挂牌", "大宗",
            "CEA", "CCER", "配额", "碳配额", "元/吨",
        )
        if any(kw in line for kw in price_kw):
            # 提取数字信息
            numbers = re.findall(r"[\d,]+\.?\d*", line)
            if numbers:
                lines.append(line[:200])
    return lines


def _extract_policy_data(text: str) -> list[str]:
    """从文本中提取政策相关段落。"""
    lines = []
    for para in text.split("。"):
        para = para.strip()
        if not para:
            continue
        policy_kw = (
            "印发", "印发", "发布", "通知", "意见", "方案", "规划",
            "碳达峰", "碳中和", "节能减排", "绿色", "低碳", "双碳",
            "实施", "试行", "暂行", "办法", "规定", "条例",
        )
        if any(kw in para for kw in policy_kw):
            lines.append(para[:200])
    return lines


def analyze_html(html: str, query_type: str = "") -> dict[str, object]:
    parser = _HtmlAnalyzer()
    try:
        parser.feed(html or "")
    except Exception:
        pass
    title = _clean(parser.title) or "（无 title）"

    # 全文拼接
    full_text = " ".join(parser._body_parts)

    # 按类型提取关键数据
    extracted: list[str] = []
    if query_type == "price":
        extracted = _extract_price_data(full_text)
    elif query_type in ("policy",):
        extracted = _extract_policy_data(full_text)

    # 正文摘要（优先取正文区域或提取的关键数据）
    snippet = ""
    if extracted:
        snippet = "；".join(extracted[:_MAX_SNIPPET])[:3000]
    else:
        snippet = full_text[:_MAX_SNIPPET] or "（无摘要）"

    return {
        "title": title,
        "headings": parser.headings[:10],
        "snippet": snippet,
        "extracted": extracted[:20],
    }


def build_conclusion(url: str, data: dict[str, object], query_type: str = "") -> str:
    headings = data.get("headings") or []
    heading_text = "、".join(headings[:5]) if headings else "（无明显标题）"

    extracted = data.get("extracted") or []
    extracted_text = ""
    if extracted:
        extracted_text = "\n关键数据：\n" + "\n".join(
            f"  - {item[:200]}" for item in extracted[:10]
        )

    snippet = str(data.get("snippet") or "")[:600]

    type_label = {
        "price": "碳价行情",
        "policy": "政策法规",
        "emission": "排放数据",
        "ccer": "CCER 数据",
        "international": "国际碳市场",
        "local": "地方双碳方案",
    }.get(query_type, "双碳资讯")

    return (
        f"【{type_label}】\n"
        f"URL：{url}\n"
        f"标题：{data.get('title')}\n"
        f"主要标题：{heading_text}\n"
        f"正文摘要：{snippet}"
        f"{extracted_text}"
    )
