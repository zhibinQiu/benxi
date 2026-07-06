"""本析首页：来源标注（检索由智能体在 tool loop 内自行调用）。"""

from __future__ import annotations

from app.services.ai_chat_service import build_ai_home_source_footer
from app.services.kg_service import KgQaContext


def test_source_footer_lists_kb_and_kg():
    footer = build_ai_home_source_footer(
        channels={"kb": True, "kg": True, "web": False},
        citations=[{"source": "local", "index": 1}, {"source": "local", "index": 2}],
        kg_context=KgQaContext(
            context_text="实体A --关系--> 实体B",
            citations=[],
            matched_entity_ids=[],
            entity_count=2,
            relation_count=1,
        ),
    )
    assert "知识库（2 条片段）" in footer
    assert "本体图谱（2 实体 / 1 关系）" in footer
    assert footer.index("本体图谱") < footer.index("知识库")
