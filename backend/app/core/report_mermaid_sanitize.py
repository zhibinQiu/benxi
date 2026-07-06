"""报告正文中的 Mermaid 围栏清洗（与前端 mermaidSanitize.js 规则对齐）。"""

from __future__ import annotations

import re

_CJK_RE = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]")
_MERMAID_FENCE_RE = re.compile(r"```\s*mermaid\s*\n([\s\S]*?)```", re.I)
_QUOTED_RE = re.compile(r'^["\'].*["\']$')
_ARROW_RE = re.compile(r"(-->|---->|---|-\.->|==>|--x|-x|->>|->)")


def _needs_node_id_quotes(token: str) -> bool:
    """流程图边上的裸节点 token（无方括号形状）含中文时需整体加引号。"""
    t = (token or "").strip()
    if not t or _QUOTED_RE.match(t):
        return False
    if _CJK_RE.search(t):
        return True
    if re.search(r"[^\w-]", t):
        return True
    return False


def _needs_quotes(text: str) -> bool:
    t = (text or "").strip()
    if not t or _QUOTED_RE.match(t):
        return False
    if _CJK_RE.search(t):
        return True
    if re.search(r"[\(\)\[\]{}<>#@/\\&|]", t):
        return True
    if re.search(r"\s[\+\-]\s", t):
        return True
    return False


def _looks_like_flowchart_node_def(text: str) -> bool:
    t = (text or "").strip()
    return bool(re.match(r'^\w+\s*[\[\(\{<]', t) or re.match(r'^"[^"]+"\s*[\[\(\{<]', t))


def _replace_mermaid_line_breaks(source: str) -> str:
    depth = 0
    result: list[str] = []
    i = 0
    s = source or ""
    while i < len(s):
        br = re.match(r"<br\s*/?>", s[i:], re.I)
        if br:
            result.append(" " if depth > 0 else "\n")
            i += br.end()
            continue
        ch = s[i]
        if ch in "[({":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        result.append(ch)
        i += 1
    return "".join(result)


def _preprocess_mermaid_source(source: str) -> str:
    expanded = _expand_mindmap_pseudo_catalog_source(source or "")
    return "\n".join(_unwrap_quoted_flowchart_node(line) for line in expanded.split("\n"))


def _quote(text: str) -> str:
    escaped = (text or "").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _unwrap_mindmap_label(text: str) -> str:
    t = (text or "").strip()
    if _QUOTED_RE.match(t):
        return t[1:-1].replace('\\"', '"')
    return t


_FLOW_EDGE_RE = re.compile(
    r"^(\s*)(.+?)\s*(<--->|<-->|<-|---->|---|-\.->|==>|--x|-x|-->|->)\s*(?:\|([^|]*?)\|)?\s*(.+?)\s*$"
)


def _unwrap_quoted_flowchart_node(line: str) -> str:
    """LLM 常输出 \"A1[\\\"标签\\\"]\"，须还原为 A1[\"标签\"]。"""
    raw = line or ""
    stripped = raw.strip()
    if not _QUOTED_RE.match(stripped):
        return raw
    inner = stripped[1:-1].replace('\\"', '"').strip()
    node_match = re.match(r"^(\w+)\s*\[((?:[^\]]|\\.)*)\]\s*$", inner)
    if not node_match:
        return raw
    node_id, label = node_match.group(1), node_match.group(2).strip()
    if not _QUOTED_RE.match(label) and _needs_quotes(label):
        label = _quote(label)
    indent = raw[: len(raw) - len(raw.lstrip())]
    return f"{indent}{node_id}[{label}]"


def _quote_flowchart_node_token(token: str) -> str:
    raw = (token or "").strip()
    if not raw or _QUOTED_RE.match(raw):
        return raw
    shape = re.match(r"^([^[\({<]+)([\[\({<].+[\]\)}>])$", raw)
    if shape:
        node_id, shape_part = shape.group(1).strip(), shape.group(2)
        bracket = re.match(r"^(\[)(.+)(\])$", shape_part)
        if bracket and _needs_quotes(bracket.group(2).strip()):
            inner = _quote(bracket.group(2).strip())
            shape_part = f"{bracket.group(1)}{inner}{bracket.group(3)}"
        if _needs_node_id_quotes(node_id):
            return f"{_quote(node_id)}{shape_part}"
        return f"{node_id}{shape_part}"
    if _needs_node_id_quotes(raw):
        return _quote(raw)
    return raw


def _sanitize_flowchart_edge_line(line: str) -> str:
    match = _FLOW_EDGE_RE.match(line)
    if not match:
        return line
    indent, left_raw, arrow, edge_label, right_raw = match.groups()
    left = _quote_flowchart_node_token(left_raw.strip())
    right = _quote_flowchart_node_token(right_raw.strip())
    if edge_label is not None:
        label = edge_label.strip()
        if label and _needs_quotes(label) and not _QUOTED_RE.match(label):
            label = _quote(label)
        edge = f"{arrow}|{label}|"
    else:
        edge = arrow
    return f"{indent}{left} {edge} {right}"


def _parse_mindmap_bracket_list(inner: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    in_quote = False
    for i, ch in enumerate(inner or ""):
        if ch == '"' and (i == 0 or inner[i - 1] != "\\"):
            in_quote = not in_quote
            continue
        if ch == "," and not in_quote:
            item = "".join(current).strip().strip("\"'")
            if item:
                items.append(item)
            current = []
            continue
        current.append(ch)
    last = "".join(current).strip().strip("\"'")
    if last:
        items.append(last)
    return items


def _expand_mindmap_pseudo_catalog_line(line: str) -> list[str]:
    """LLM 常把 mindmap 子节点写成 \"分类\"：[\"项1\", \"项2\"]，须展开为层级缩进。"""
    raw = line or ""
    stripped = raw.strip()
    if not stripped or stripped.lower().startswith("mindmap"):
        return [raw]
    indent = raw[: len(raw) - len(raw.lstrip())]
    content = stripped
    if _QUOTED_RE.match(content):
        content = content[1:-1].replace('\\"', '"')
    catalog = re.match(r'^(?:"([^"]+)"|([^\s：:\[]+?))\s*[：:]\s*\[(.+)\]\s*$', content)
    if not catalog:
        return [raw]
    label = (catalog.group(1) or catalog.group(2) or "").strip()
    items = _parse_mindmap_bracket_list(catalog.group(3))
    if not label or not items:
        return [raw]
    child_indent = f"{indent}  "
    result = [f"{indent}{label}"]
    for item in items:
        text = item.strip()
        if not text:
            continue
        result.append(f"{child_indent}{text}")
    return result


def _expand_mindmap_pseudo_catalog_source(source: str) -> str:
    if not re.match(r"^\s*mindmap\b", source or "", re.I):
        return source or ""
    return "\n".join(
        line
        for raw_line in (source or "").split("\n")
        for line in _expand_mindmap_pseudo_catalog_line(raw_line)
    )


def _sanitize_mermaid_line(line: str, diagram_type: str) -> str:
    raw = line or ""
    stripped = raw.strip()
    if not stripped or stripped.startswith("%%"):
        return raw
    if diagram_type == "mindmap":
        if stripped.startswith("mindmap"):
            return raw
        indent = raw[: len(raw) - len(raw.lstrip())]
        root_match = re.match(r"^(\w+\(\()(.+)(\)\))\s*$", stripped)
        if root_match:
            inner = _unwrap_mindmap_label(root_match.group(2))
            return f"{indent}{root_match.group(1)}{inner}{root_match.group(3)}"
        return f"{indent}{_unwrap_mindmap_label(stripped)}"
    if diagram_type == "flowchart":
        if re.match(r"^(flowchart|graph)\b", stripped, re.I):
            return re.sub(r"^graph\b", "flowchart", raw, count=1, flags=re.I)
        if re.match(r"^(subgraph|end|style|class|click|direction)\b", stripped, re.I):
            return raw
        raw = _unwrap_quoted_flowchart_node(raw)
        stripped = raw.strip()
        if _ARROW_RE.search(stripped) or re.search(r"<-->", stripped):
            sanitized = _sanitize_flowchart_edge_line(raw)
            return sanitized if sanitized != raw else raw
        if _needs_quotes(stripped) and not _looks_like_flowchart_node_def(stripped):
            indent = raw[: len(raw) - len(raw.lstrip())]
            return f"{indent}{_quote(stripped)}"
        return raw
    if diagram_type == "sequence":
        colon = stripped.find(":")
        if colon > 0:
            head, msg = stripped[:colon], stripped[colon + 1 :].strip()
            if msg and _needs_quotes(msg) and not _QUOTED_RE.match(msg):
                if _ARROW_RE.search(head) or head.strip().lower().startswith("note"):
                    return f"{raw[:colon + 1]} {_quote(msg)}"
        return raw
    return raw


def _detect_diagram_type(source: str) -> str:
    for raw in (source or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("%%"):
            continue
        head = line.split()[0].lower()
        if head in ("flowchart", "graph"):
            return "flowchart"
        if head == "sequencediagram":
            return "sequence"
        if head == "mindmap":
            return "mindmap"
        if head in ("gantt", "timeline"):
            return "gantt"
        if head.startswith("statediagram"):
            return "state"
        return head
    return ""


def sanitize_mermaid_source(source: str) -> str:
    text = _replace_mermaid_line_breaks(_preprocess_mermaid_source(source or ""))
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return ""
    diagram_type = _detect_diagram_type(text)
    if diagram_type == "sequence" and not text.startswith("sequenceDiagram"):
        text = re.sub(r"^sequenceDiagram\b", "sequenceDiagram", text, flags=re.I)
        if not text.startswith("sequenceDiagram"):
            text = re.sub(r"^sequencediagram\b", "sequenceDiagram", text, flags=re.I)
    lines = text.split("\n")
    return "\n".join(_sanitize_mermaid_line(line, diagram_type) for line in lines).strip()


def sanitize_report_markdown_mermaid(markdown: str) -> str:
    """清洗报告 Markdown 中全部 mermaid 围栏。"""

    def _repl(match: re.Match[str]) -> str:
        body = sanitize_mermaid_source(match.group(1))
        return f"```mermaid\n{body}\n```"

    return _MERMAID_FENCE_RE.sub(_repl, markdown or "")
