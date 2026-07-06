"""技能开发 playbook 与脚本校验。"""

from __future__ import annotations

import pytest

from app.core.exceptions import AppError
from app.core.skill_dev_playbook import (
    ensure_script_extra_files,
    enrich_skill_repair_reason,
    format_skill_script_repair_hint,
    normalize_skill_slug,
    slugify_skill_name,
    validate_uploaded_skill_script,
)


def test_slugify_skill_name_normalizes_underscores_and_case():
    assert slugify_skill_name("Carbon_Price_Scraper") == "carbon-price-scraper"
    assert normalize_skill_slug("carbon_price_scraper") == "carbon-price-scraper"


def test_slugify_rejects_empty_chinese_only():
    with pytest.raises(AppError):
        normalize_skill_slug("碳价爬取")


def test_validate_blocks_requests():
    with pytest.raises(AppError, match="不允许"):
        validate_uploaded_skill_script(
            "import requests\nrequests.get('http://example.com')"
        )


def test_ensure_script_extra_files_injects_scaffold():
    files = ensure_script_extra_files(None, needs_url=True)
    assert "main.py" in files
    assert "skill_runtime.finish" in files["main.py"]
    assert "fetch_text" in files["main.py"]


def test_ensure_script_extra_files_replaces_invalid_main_with_scaffold():
    bad = "import requests\nrequests.get('http://example.com')"
    files = ensure_script_extra_files({"main.py": bad}, needs_url=True)
    assert "skill_runtime.finish" in files["main.py"]
    assert "fetch_utils.py" in files
    assert "requests" not in files["main.py"]


def test_validate_allows_re_compile():
    code = """
import re
import skill_runtime
pat = re.compile(r"price")
skill_runtime.finish("ok")
"""
    validate_uploaded_skill_script(code)


def test_format_skill_script_repair_hint_json():
    hint = format_skill_script_repair_hint(
        '脚本须在最后输出一行 JSON，例如 {"conclusion":"分析结论"}'
    )
    assert "skill_runtime.finish" in hint


def test_enrich_skill_repair_reason_parses_api_error():
    raw = "400: {'code': 400, 'message': 'skill name 仅允许小写字母、数字与连字符（如 pdf-tools）'}"
    hint = enrich_skill_repair_reason(raw)
    assert "carbon-market" in hint or "slug" in hint
