"""知识问答：文档嵌入图改写为平台鉴权代理 URL。"""

from app.skills.builtin.handlers import (
    _ensure_platform_images_in_answer,
    _knowledge_qa_format_hits,
    _normalize_chat_image_url,
    _platform_citation_image_url,
    _rewrite_media_for_chat,
)


def test_normalize_knowflow_document_image_to_platform_proxy():
    assert _normalize_chat_image_url(
        "/v1/document/image/ds1-chunk1"
    ) == "/api/v1/knowledge/citations/images/ds1-chunk1"
    assert _normalize_chat_image_url(
        "https://knowflow.example/v1/document/image/abc%2Fdef"
    ) == "/api/v1/knowledge/citations/images/abc/def"


def test_keep_public_https_and_data_uri():
    assert _normalize_chat_image_url("https://cdn.example/a.png") == "https://cdn.example/a.png"
    data = "data:image/png;base64,AAAA"
    assert _normalize_chat_image_url(data) == data


def test_rewrite_markdown_and_html_img():
    text = (
        '见图 ![图1](/v1/document/image/img-1) 与 '
        '<img src="/v1/document/image/img-2" alt="图2" />'
    )
    out = _rewrite_media_for_chat(text)
    assert "![图1](/api/v1/knowledge/citations/images/img-1)" in out
    assert "![图2](/api/v1/knowledge/citations/images/img-2)" in out
    assert "<img" not in out.lower()


def test_format_hits_appends_image_id_and_inline():
    body, cites = _knowledge_qa_format_hits(
        [
            {
                "title": "制度.pdf",
                "content": "考勤规则……",
                "document_id": "d1",
                "image_id": "shot-1",
                "inline_images": [{"url": "/v1/document/image/inline-1", "alt": "表"}],
                "preview_available": True,
                "source": "knowflow",
            }
        ]
    )
    proxy = _platform_citation_image_url("shot-1")
    assert proxy in body
    assert "/api/v1/knowledge/citations/images/inline-1" in body
    assert cites[0]["image_id"] == "shot-1"
    assert cites[0]["inline_images"][0]["url"].endswith("inline-1")


def test_ensure_platform_images_reappended_when_model_drops():
    notebook = "材料\n\n![文档截图](/api/v1/knowledge/citations/images/keep-me)\n"
    answer = "根据材料，考勤需打卡。"
    out = _ensure_platform_images_in_answer(answer, notebook)
    assert "考勤需打卡" in out
    assert "/api/v1/knowledge/citations/images/keep-me" in out
    assert "相关文档图" in out
