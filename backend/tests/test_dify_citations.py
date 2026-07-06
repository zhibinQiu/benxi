from app.integrations.agent_chat_client import parse_dify_citations


def test_parse_retriever_resources():
    cites = parse_dify_citations(
        {
            "event": "message_end",
            "metadata": {
                "retriever_resources": [
                    {
                        "position": 1,
                        "document_name": "碳排放核算指南",
                        "document_id": "doc-1",
                        "segment_id": "seg-1",
                        "score": 0.92,
                        "content": "范围一排放指企业拥有或控制的排放源。",
                    },
                    {
                        "position": 2,
                        "document_name": "全国碳市场政策汇编",
                        "content": "纳入行业清单每年更新。",
                    },
                ]
            },
        }
    )
    assert len(cites) == 2
    assert cites[0]["title"] == "碳排放核算指南"
    assert cites[0]["snippet"].startswith("范围一")
    assert cites[0]["score"] == 0.92


def test_parse_empty_metadata():
    assert parse_dify_citations({"event": "message_end"}) == []


def test_merge_citations_same_document():
    cites = parse_dify_citations(
        {
            "event": "message_end",
            "metadata": {
                "retriever_resources": [
                    {
                        "position": 1,
                        "document_name": "碳排放核算指南",
                        "document_id": "doc-1",
                        "segment_id": "seg-1",
                        "score": 0.8,
                        "content": "第一段引用内容。",
                    },
                    {
                        "position": 2,
                        "document_name": "碳排放核算指南",
                        "document_id": "doc-1",
                        "segment_id": "seg-2",
                        "score": 0.95,
                        "content": "第二段引用内容。",
                    },
                ]
            },
        }
    )
    assert len(cites) == 1
    assert cites[0]["title"] == "碳排放核算指南"
    assert cites[0]["score"] == 0.95
    assert "第一段引用内容" in cites[0]["snippet"]
    assert "第二段引用内容" in cites[0]["snippet"]
