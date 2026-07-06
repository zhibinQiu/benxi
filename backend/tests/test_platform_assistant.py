"""平台 AI 助手人设常量。"""

from __future__ import annotations

from app.core.platform_assistant import (
    PLATFORM_AI_ASSISTANT_NAME,
    assistant_ai_home_persona,
    assistant_support_persona,
    assistant_user_communication_style,
)


def test_platform_assistant_name():
    assert PLATFORM_AI_ASSISTANT_NAME == "小析"


def test_persona_intros_use_xiaoxi():
    assert "小析" in assistant_support_persona()
    assert "小析" in assistant_ai_home_persona()


def test_user_communication_style_covers_structure_and_tone():
    style = assistant_user_communication_style()
    assert "温柔" in style
    assert "mermaid" in style
    assert "条理" in style or "结构" in style
