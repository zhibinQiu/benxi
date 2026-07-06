"""本析智能 — 继续提问推荐。"""

from unittest.mock import patch

from app.schemas.ai_chat import AiChatMessage
from app.services.ai_chat_service import generate_follow_up_questions


@patch("app.integrations.deepseek_client.is_configured", return_value=True)
@patch("app.integrations.deepseek_client.chat_completion_sync")
def test_generate_follow_up_questions_parses_json(mock_chat, _configured):
    mock_chat.return_value = (
        '{"questions":["碳市场纳入行业有哪些？","配额分配规则是什么？",'
        '"全国碳市场管理办法约束哪些指标？"]}'
    )
    out = generate_follow_up_questions(
        user_message="全国碳市场管理办法约束哪些指标？",
        assistant_answer="全国碳市场主要约束温室气体排放总量与配额履约等指标，企业需按期清缴。",
        history=[
            AiChatMessage(role="user", content="全国碳市场管理办法约束哪些指标？"),
        ],
    )
    assert len(out) == 2
    assert out[0].endswith("？")
    assert "配额分配" in out[1]


@patch("app.integrations.deepseek_client.is_configured", return_value=True)
def test_generate_follow_up_questions_skips_short_answer(_configured):
    assert (
        generate_follow_up_questions(
            user_message="你好",
            assistant_answer="你好",
        )
        == []
    )
