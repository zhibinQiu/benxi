"""Agent Skill 记忆触发与 Skill 加载校验。"""

from __future__ import annotations

from app.services.agent_skill_router import (
    extract_memory_note,
    is_skill_management_message,
    should_read_memory,
    should_write_memory,
    validate_uploaded_skill_load,
)
from app.skills.types import SkillSource


def test_memory_read_trigger():
    assert should_read_memory("还记得上次说的偏好吗") is True
    assert should_read_memory("碳价是多少") is False


def test_memory_write_trigger_and_extract():
    msg = "请记住我喜欢简洁回答"
    assert should_write_memory(msg) is True
    assert "简洁" in extract_memory_note(msg)


def test_skill_management_message():
    assert is_skill_management_message("帮我创建一个 skills，计算三位数乘法") is True
    assert is_skill_management_message("画一个审批流程图") is False


def test_validate_uploaded_skill_load_blocks_skill_creation():
    ok, reason = validate_uploaded_skill_load(
        user_message="帮我创建一个 skills，可以计算三位数乘法",
        skill_name="mermaid-diagram",
        skill_description="生成 Mermaid 流程图与思维导图",
        skill_source=SkillSource.UPLOADED,
    )
    assert ok is False
    assert "create_uploaded_skill" in reason


def test_validate_uploaded_skill_load_blocks_builtin():
    ok, reason = validate_uploaded_skill_load(
        user_message="联网查一下碳价",
        skill_name="web-search",
        skill_description="联网搜索",
        skill_source=SkillSource.BUILTIN,
    )
    assert ok is False
    assert "内置" in reason


def test_validate_uploaded_skill_load_allows_explicit_name():
    ok, reason = validate_uploaded_skill_load(
        user_message="按 mermaid-diagram 的流程帮我画流程图",
        skill_name="mermaid-diagram",
        skill_description="生成 Mermaid 流程图",
        skill_source=SkillSource.UPLOADED,
    )
    assert ok is True
    assert reason == ""


def test_validate_uploaded_skill_load_allows_matching_task():
    ok, _ = validate_uploaded_skill_load(
        user_message="帮我把这段制度整理成流程图",
        skill_name="mermaid-diagram",
        skill_description="生成 Mermaid 流程图、时序图与思维导图",
        skill_source=SkillSource.UPLOADED,
    )
    assert ok is True


def test_validate_uploaded_skill_load_allows_url_page_task():
    ok, reason = validate_uploaded_skill_load(
        user_message="帮我看一下 https://example.com 这个页面讲什么",
        skill_name="web-page-insight",
        skill_description=(
            "在沙箱中拉取公开网页并在内存中分析标题、摘要与结构要点；"
            "通过 run_skill_script 执行"
        ),
        skill_source=SkillSource.UPLOADED,
    )
    assert ok is True
    assert reason == ""


def test_validate_uploaded_skill_load_allows_planned_skill():
    ok, reason = validate_uploaded_skill_load(
        user_message="123乘以456等于多少",
        skill_name="three-digit-multiplier",
        skill_description="三位数乘法竖式计算",
        skill_source=SkillSource.UPLOADED,
        planned_skill="three-digit-multiplier",
    )
    assert ok is True
    assert reason == ""


def test_validate_uploaded_skill_load_allows_created_skill_after_skill_mgmt():
    """创建 Skill 后同轮 load 刚创建的包，不应被 Skill 管理意图拦截。"""
    ok, reason = validate_uploaded_skill_load(
        user_message="帮我创建一个 skill，从碳市场网爬取碳价数据",
        skill_name="carbon-price-scraper",
        skill_description="从碳市场网爬取全国碳市场价格行情",
        skill_source=SkillSource.UPLOADED,
        created_skills=("carbon-price-scraper",),
    )
    assert ok is True
    assert reason == ""


def test_validate_uploaded_skill_load_allows_domain_in_message():
    ok, reason = validate_uploaded_skill_load(
        user_message="从碳市场网（tanshichang.cn）爬取全国碳市场最新价格行情",
        skill_name="carbon-price-scraper",
        skill_description="从碳市场网爬取全国碳市场价格行情数据",
        skill_source=SkillSource.UPLOADED,
    )
    assert ok is True
    assert reason == ""


def test_validate_uploaded_skill_load_allows_math_task():
    ok, reason = validate_uploaded_skill_load(
        user_message="123乘以456等于多少",
        skill_name="three-digit-multiplier",
        skill_description="按 SKILL.md 流程计算三位数乘法，展示竖式步骤",
        skill_source=SkillSource.UPLOADED,
    )
    assert ok is True
    assert reason == ""


def test_validate_uploaded_skill_load_allows_chinese_keyword_overlap():
    ok, reason = validate_uploaded_skill_load(
        user_message="计算三位数乘法",
        skill_name="three-digit-multiplier",
        skill_description="按 SKILL.md 流程计算三位数乘法，展示竖式步骤",
        skill_source=SkillSource.UPLOADED,
    )
    assert ok is True
    assert reason == ""
