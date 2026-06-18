"""核心文本与 LLM 解析工具。"""

from app.core.llm_parse import parse_llm_json
from app.core.text_utils import truncate_text


def test_truncate_text_short_unchanged():
    assert truncate_text("hello", 10) == "hello"


def test_truncate_text_long():
    result = truncate_text("a" * 100, 50)
    assert len(result) == 50
    assert result.endswith("…（后文已截断）")


def test_parse_llm_json_plain():
    assert parse_llm_json('{"ok": true}') == {"ok": True}


def test_parse_llm_json_fence():
    raw = '```json\n{"items": [1]}\n```'
    assert parse_llm_json(raw) == {"items": [1]}


def test_parse_llm_json_embedded():
    raw = '说明如下：{"summary": "x"} 完毕'
    assert parse_llm_json(raw) == {"summary": "x"}
