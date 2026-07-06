"""agentkit-subagent context 测试。"""

from agentkit_subagent import normalize_queries


def test_normalize_queries_fallback_task():
    assert normalize_queries("hello world", None) == ["hello world"]


def test_normalize_queries_dedup():
    out = normalize_queries("", ["a", "a", "bb"])
    assert out == ["a", "bb"]
