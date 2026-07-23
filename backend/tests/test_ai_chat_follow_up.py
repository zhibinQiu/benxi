"""本析智能 — 继续提问推荐。"""

from unittest.mock import patch

from app.schemas.ai_chat import AiChatMessage
from app.services.ai_chat_service import (
    generate_follow_up_questions,
    _is_low_quality_follow_up,
)


@patch("app.integrations.deepseek_client.is_configured", return_value=True)
@patch("app.integrations.deepseek_client.chat_completion_sync")
def test_generate_follow_up_questions_parses_json(mock_chat, _configured):
    mock_chat.return_value = (
        '{"questions":["碳市场纳入行业有哪些？","配额分配规则是什么？",'
        '"全国碳市场管理办法约束哪些指标？"]}'
    )
    out = generate_follow_up_questions(
        user_message="全国碳市场管理办法约束哪些指标？",
        assistant_answer=(
            "全国碳市场主要约束温室气体排放总量与配额履约等指标，"
            "企业需按期清缴。覆盖发电等重点排放行业，并逐步扩大范围。"
        ),
        history=[
            AiChatMessage(role="user", content="全国碳市场管理办法约束哪些指标？"),
        ],
    )
    assert len(out) == 2
    assert out[0].endswith("？")
    assert "配额分配" in out[1]
    # 与用户原问同义的第三条应被过滤
    assert all("管理办法约束哪些指标" not in q for q in out)


@patch("app.integrations.deepseek_client.is_configured", return_value=True)
def test_generate_follow_up_questions_skips_short_answer(_configured):
    assert (
        generate_follow_up_questions(
            user_message="你好",
            assistant_answer="你好",
        )
        == []
    )


@patch("app.integrations.deepseek_client.is_configured", return_value=True)
@patch("app.integrations.deepseek_client.chat_completion_sync", return_value=None)
def test_generate_follow_up_questions_no_low_quality_fallback(mock_chat, _configured):
    out = generate_follow_up_questions(
        user_message="全国碳市场怎么履约？",
        assistant_answer="履约需按期清缴配额，不足部分可购买，多余可结转或出售。" * 2,
    )
    assert out == []
    mock_chat.assert_called_once()


def test_normalize_follow_up_strips_markdown():
    from app.services.ai_chat_service import _normalize_follow_up_question

    assert _normalize_follow_up_question("**配额**如何购买？") == "配额如何购买"
    assert _normalize_follow_up_question("`CEA` 价格怎么查") == "CEA 价格怎么查"
    assert "#" not in _normalize_follow_up_question("## 下一步做什么")


def test_is_low_quality_follow_up_filters_generic_and_copy():
    answer = "履约需按期清缴配额，不足部分可购买。"
    assert _is_low_quality_follow_up(
        "还有什么？", user_message="怎么履约", answer=answer
    )
    assert _is_low_quality_follow_up(
        "履约需按期清缴配额，不足部分可购买？",
        user_message="怎么履约",
        answer=answer,
    )
    assert not _is_low_quality_follow_up(
        "配额不足时如何购买？",
        user_message="怎么履约",
        answer=answer,
    )
