"""Dify 流式 answer 增量/累积两种格式的 delta 提取。"""


def _extract_delta(accumulated: str, chunk: str) -> tuple[str, str]:
    """与 agent_chat_client.iter_agent_chat_stream 中逻辑一致。"""
    if accumulated and chunk.startswith(accumulated):
        delta = chunk[len(accumulated) :]
        return chunk, delta
    return accumulated + chunk, chunk


def test_incremental_chunks():
    acc = ""
    full = ""
    for piece in ["## 标题\n\n", "正文 **加粗**", " 与图表"]:
        acc, delta = _extract_delta(acc, piece)
        full += delta
    assert full == "## 标题\n\n正文 **加粗** 与图表"
    assert acc == full


def test_cumulative_chunks():
    acc = ""
    full = ""
    for piece in ["Hel", "Hello", "Hello world"]:
        acc, delta = _extract_delta(acc, piece)
        full += delta
    assert full == "Hello world"
