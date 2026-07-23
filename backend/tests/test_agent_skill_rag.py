"""Skill Embedding 语义召回测试。"""

from __future__ import annotations

import numpy as np
import pytest

from app.services.agent_skill_rag import (
    invalidate_skill_embedding_index,
    rank_skills_by_embedding,
    skill_routing_document,
)
from app.skills.types import SkillDefinition, SkillSource


def _skill(
    name: str,
    *,
    title: str = "",
    description: str = "",
    use_when: str = "",
) -> SkillDefinition:
    return SkillDefinition(
        name=name,
        title=title or name,
        description=description,
        source=SkillSource.BUILTIN,
        use_when=use_when,
        catalog_tier="resident",
    )


def _lex_embed(texts: list[str], **_kwargs) -> list[np.ndarray]:
    """确定性词袋向量：共享中文词元则 cosine 更高。"""
    vocab = [
        "碳",
        "配额",
        "价格",
        "行情",
        "政策",
        "股票",
        "估值",
        "财务",
        "知识",
        "问答",
        "文档",
        "文件夹",
    ]
    out: list[np.ndarray] = []
    for text in texts:
        v = np.zeros(len(vocab), dtype=np.float32)
        t = text or ""
        for i, token in enumerate(vocab):
            if token in t:
                v[i] = 1.0
        if float(np.linalg.norm(v)) < 1e-6:
            v[0] = 0.01
        out.append(v)
    return out


@pytest.fixture(autouse=True)
def _reset_index():
    invalidate_skill_embedding_index()
    yield
    invalidate_skill_embedding_index()


def test_rank_skills_by_embedding_synonym_prefers_carbon(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_skill_rag.get_settings",
        lambda: type(
            "S",
            (),
            {
                "agent_skill_rag_enabled": True,
                "agent_skill_rag_min_similarity": 0.1,
            },
        )(),
    )
    monkeypatch.setattr(
        "app.services.agent_skill_rag._get_credentials",
        lambda _db: ("https://emb.example/v1", "sk-test", "test-emb"),
    )
    monkeypatch.setattr("app.services.agent_skill_rag.embed_texts", _lex_embed)

    skills = [
        _skill(
            "carbon-qa",
            title="双碳问答",
            use_when="碳价行情、碳交易、碳配额价格、碳排放核算",
        ),
        _skill(
            "stock-deep-analysis",
            title="个股深度",
            use_when="单只股票财务估值与成长逻辑",
        ),
        _skill(
            "knowledge-qa",
            title="知识问答",
            use_when="知识库与联网交叉验证问答",
        ),
    ]
    ranked = rank_skills_by_embedding(None, "碳配额价格怎么样", skills, limit=3)
    assert ranked is not None
    assert ranked[0][1].name == "carbon-qa"
    assert ranked[0][0] > ranked[-1][0]


def test_rank_skills_by_embedding_returns_none_without_credentials(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_skill_rag.get_settings",
        lambda: type(
            "S",
            (),
            {
                "agent_skill_rag_enabled": True,
                "agent_skill_rag_min_similarity": 0.42,
            },
        )(),
    )
    monkeypatch.setattr(
        "app.services.agent_skill_rag._get_credentials",
        lambda _db: None,
    )
    skills = [_skill("carbon-qa", use_when="碳价")]
    assert rank_skills_by_embedding(None, "碳价", skills) is None


def test_rank_skills_keyword_fallback_when_embedding_none(monkeypatch):
    from app.services.agent_skill_routing import _rank_skills_for_routing

    monkeypatch.setattr(
        "app.services.agent_skill_rag.rank_skills_by_embedding",
        lambda *a, **k: None,
    )
    skills = [
        _skill("carbon-qa", use_when="碳价行情碳交易政策"),
        _skill("stock-deep-analysis", use_when="个股财务估值"),
    ]
    ranked = _rank_skills_for_routing(None, "全国碳市场最新政策", skills, limit=5)
    assert ranked
    assert any(sk.name == "carbon-qa" for _, sk in ranked)


def test_invalidate_skill_embedding_index(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_skill_rag.get_settings",
        lambda: type(
            "S",
            (),
            {
                "agent_skill_rag_enabled": True,
                "agent_skill_rag_min_similarity": 0.1,
            },
        )(),
    )
    monkeypatch.setattr(
        "app.services.agent_skill_rag._get_credentials",
        lambda _db: ("https://emb.example/v1", "sk-test", "test-emb"),
    )
    calls = {"n": 0}

    def counting_embed(texts, **kwargs):
        calls["n"] += 1
        return _lex_embed(texts, **kwargs)

    monkeypatch.setattr("app.services.agent_skill_rag.embed_texts", counting_embed)
    skills = [_skill("carbon-qa", use_when="碳价行情")]
    assert rank_skills_by_embedding(None, "碳价", skills) is not None
    assert rank_skills_by_embedding(None, "碳价", skills) is not None
    # 第二次查询复用索引，只再 embed query，不重建文档矩阵
    n_after_reuse = calls["n"]
    invalidate_skill_embedding_index()
    assert rank_skills_by_embedding(None, "碳价", skills) is not None
    assert calls["n"] > n_after_reuse


def test_skill_routing_document_prefers_skills_md():
    skill = _skill("carbon-qa", description="fallback-only")
    doc = skill_routing_document(skill)
    assert "carbon-qa" in doc or "双碳" in doc or "碳" in doc
    assert "fallback-only" not in doc
