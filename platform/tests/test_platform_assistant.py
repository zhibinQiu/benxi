"""平台 AI 助手人设常量。"""

from __future__ import annotations

from app.core.platform_assistant import (
    PLATFORM_AI_ASSISTANT_NAME,
    assistant_ai_home_persona,
    assistant_support_persona,
)


def test_platform_assistant_name():
    assert PLATFORM_AI_ASSISTANT_NAME == "小析"


def test_persona_intros_use_xiaoxi():
    assert "小析" in assistant_support_persona()
    assert "小析" in assistant_ai_home_persona()
