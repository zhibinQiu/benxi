"""agent_tool_args 单元测试。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.agent_tool_args import (
    TOOL_ARG_MODELS,
    TOOL_DEFINITIONS,
    build_function_tool_spec,
    format_validation_error,
    tool_parameters_schema,
    validate_tool_arguments,
)
from app.services.agent_tool_registry import _TOOL_CATEGORIES
from app.services.skill_chat_service import ATOMIC_TOOL_WEB_SEARCH


def test_all_registry_tools_have_pydantic_models():
    missing = set(_TOOL_CATEGORIES) - set(TOOL_ARG_MODELS)
    assert not missing, f"missing models: {sorted(missing)}"
    assert len(TOOL_DEFINITIONS) == len(TOOL_ARG_MODELS)


def test_validate_web_search_rejects_empty_query():
    params, err = validate_tool_arguments(ATOMIC_TOOL_WEB_SEARCH, {"query": "  "})
    assert params is None
    assert err and "参数无效" in err


def test_validate_web_search_accepts_valid():
    params, err = validate_tool_arguments(
        ATOMIC_TOOL_WEB_SEARCH, {"query": "全国碳市场最新价格", "max_items": 5}
    )
    assert err is None
    assert params == {"query": "全国碳市场最新价格", "max_items": 5}


def test_validate_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        TOOL_ARG_MODELS[ATOMIC_TOOL_WEB_SEARCH].model_validate(
            {"query": "x", "foo": "bar"}
        )


def test_validate_unregistered_tool_fails():
    params, err = validate_tool_arguments("not_a_real_tool", {"x": 1})
    assert params is None
    assert "未注册" in (err or "")


def test_create_skill_uses_skill_md_body():
    params, err = validate_tool_arguments(
        "create_uploaded_skill",
        {
            "name": "demo",
            "description": "test",
            "skill_md_body": "# Demo",
        },
    )
    assert err is None
    assert params and params["skill_md_body"] == "# Demo"


def test_compact_schema_omits_titles():
    schema = tool_parameters_schema(TOOL_ARG_MODELS[ATOMIC_TOOL_WEB_SEARCH])
    assert "title" not in str(schema)
    assert schema["required"] == ["query"]


def test_build_function_tool_spec():
    desc, model = TOOL_DEFINITIONS[ATOMIC_TOOL_WEB_SEARCH]
    spec = build_function_tool_spec(
        name="web_search",
        description=desc,
        args_model=model,
    )
    assert spec["function"]["name"] == "web_search"
    assert spec["function"]["parameters"]["properties"]["query"]["type"] == "string"


def test_format_validation_error():
    _, err = validate_tool_arguments("run_tool_batch", {"steps": []})
    assert err
    assert "参数无效" in err


def test_empty_tool_accepts_no_fields():
    params, err = validate_tool_arguments("browser_snapshot", {})
    assert err is None
    assert params == {}


def test_empty_tool_rejects_extra_fields():
    params, err = validate_tool_arguments("read_agent_memory", {"note": "x"})
    assert params is None
    assert err
