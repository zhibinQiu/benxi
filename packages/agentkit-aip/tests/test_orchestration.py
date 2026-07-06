"""agentkit-aip orchestration 测试。"""

from agentkit_aip.orchestration import best_reply_from_hops, merge_hop_citations


def test_merge_hop_citations_dedup():
    merged = merge_hop_citations(
        [
            [{"url": "https://a", "title": "A"}],
            [{"url": "https://a", "title": "A"}],
        ]
    )
    assert len(merged) == 1


def test_best_reply_from_hops():
    text = best_reply_from_hops([None, {"reply": "hello"}])
    assert text == "hello"
