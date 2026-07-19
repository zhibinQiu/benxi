"""平台 AI 助手人设常量。"""

from __future__ import annotations

from app.core.platform_assistant import (
    PLATFORM_AI_ASSISTANT_NAME,
    assistant_ai_home_persona,
    assistant_completion_first_principle,
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
    assert "warm" in style.lower() or "温柔" in style
    assert "mermaid" in style
    assert "Structure" in style or "条理" in style or "结构" in style


def test_completion_first_principle_is_explicit():
    text = assistant_completion_first_principle()
    assert "完成用户的要求" in text
    assert "道德" in text and "法律" in text
    assert "基本原则" in text
