"""report_mermaid_sanitize 单元测试。"""

from __future__ import annotations

from app.core.report_mermaid_sanitize import (
    sanitize_mermaid_source,
    sanitize_report_markdown_mermaid,
)


def test_sanitize_flowchart_llm_quoted_node_wrappers():
    src = 'flowchart TD\n    "A1[\\"省能源局\\"]"\n    A1 --> B1'
    out = sanitize_mermaid_source(src)
    assert 'A1["省能源局"]' in out
    assert '"A1[' not in out


def test_sanitize_flowchart_bidirectional_arrow():
    src = "flowchart TD\nC1 <--> C2"
    out = sanitize_mermaid_source(src)
    assert "C1 <--> C2" in out
    assert '"C1 <"' not in out


def test_sanitize_flowchart_chinese_edge_ids():
    src = "flowchart TD\n虚拟电厂 --> 云平台"
    out = sanitize_mermaid_source(src)
    assert '"虚拟电厂"' in out
    assert '"云平台"' in out


def test_sanitize_flowchart_chinese_id_with_shape():
    src = 'flowchart TD\n虚拟电厂[节点] --> B["云平台"]'
    out = sanitize_mermaid_source(src)
    assert '"虚拟电厂"' in out
    assert '"节点"' in out


def test_sanitize_flowchart_chinese_bare_nodes():
    src = (
        "flowchart TD\n"
        "虚拟电厂\n"
        'A["调度中心"] --> B["云平台"]'
    )
    out = sanitize_mermaid_source(src)
    assert '"虚拟电厂"' in out
    assert "A[" in out


def test_sanitize_mindmap_pseudo_catalog_lines():
    src = (
        'mindmap\n'
        '  "根"\n'
        '    "\\"分布式电源\\"：[\\"分布式光伏\\", \\"分散式风电\\"]"'
    )
    out = sanitize_mermaid_source(src)
    assert '"分布式电源"' in out
    assert '"分布式光伏"' in out
    assert '"分散式风电"' in out
    assert '：["' not in out


def test_sanitize_mindmap_chinese_lines():
    src = "mindmap\n  root((主题))\n    技术架构\n    市场机制"
    out = sanitize_mermaid_source(src)
    assert '"技术架构"' in out
    assert '"市场机制"' in out


def test_sanitize_report_markdown_fence():
    md = "正文\n\n```mermaid\nmindmap\n  虚拟电厂\n```\n\n结尾"
    out = sanitize_report_markdown_mermaid(md)
    assert '"虚拟电厂"' in out
    assert "结尾" in out
