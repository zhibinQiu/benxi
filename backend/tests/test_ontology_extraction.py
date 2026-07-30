"""本体 TBox LLM 发现：discover 不写库 / apply 写入。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.ontology_extraction_service import (
    apply_ontology_candidates,
    discover_and_merge_ontology,
    discover_ontology_candidates,
    looks_like_instance_type,
)


def test_looks_like_instance_type_filters_named_cases():
    assert looks_like_instance_type("report_2024", "2024年报告") is True
    assert looks_like_instance_type("boiler_03", "第3号锅炉") is True
    assert looks_like_instance_type("gb_t_32151", "国标") is True
    assert looks_like_instance_type("enterprise", "企业") is False
    assert looks_like_instance_type("person", "人员") is False


def test_discover_rejects_short_text():
    ontology = MagicMock()

    async def _run():
        with (
            patch(
                "app.services.ontology_extraction_service.is_configured",
                return_value=True,
            ),
            pytest.raises(HTTPException) as ei,
        ):
            await discover_ontology_candidates(
                ontology, title="t", text="短文本"
            )
        assert ei.value.status_code == 400

    asyncio.run(_run())


def test_discover_candidates_do_not_write():
    ontology = MagicMock()
    ontology.list_entity_types = AsyncMock(
        return_value=[
            SimpleNamespace(code="person", label="人员", property_schema={}),
        ]
    )
    ontology.list_relation_types = AsyncMock(return_value=[])
    ontology._store = MagicMock()
    ontology._store.list_alt_labels = AsyncMock(return_value=[])
    ontology.create_entity_type = AsyncMock()
    ontology.resolve_or_merge_entity_type = AsyncMock()
    ontology.create_relation_type = AsyncMock()

    llm_json = """
    {
      "entity_types": [
        {"code": "device", "label": "设备", "properties": [{"name": "model", "type": "string"}]},
        {"code": "person", "label": "员工"}
      ],
      "relation_types": [
        {
          "code": "owns",
          "label": "拥有",
          "domain_types": ["person"],
          "range_types": ["device"]
        }
      ]
    }
    """

    async def _run():
        with (
            patch(
                "app.services.ontology_extraction_service.is_configured",
                return_value=True,
            ),
            patch(
                "app.services.ontology_extraction_service.chat_completion_sync",
                return_value=llm_json,
            ),
        ):
            out = await discover_ontology_candidates(
                ontology,
                title="测",
                text="x" * 80,
            )
        assert out["stats"]["entity_candidates"] >= 1
        codes = {e["code"]: e for e in out["entity_types"]}
        assert codes["device"]["action"] == "create"
        assert codes["device"]["selected"] is True
        assert codes["person"]["action"] in ("exists", "merge")
        owns = next(r for r in out["relation_types"] if r["code"] == "owns")
        assert owns["action"] == "create"
        ontology.create_entity_type.assert_not_called()
        ontology.resolve_or_merge_entity_type.assert_not_called()
        ontology.create_relation_type.assert_not_called()

    asyncio.run(_run())


def test_apply_writes_selected_candidates():
    ontology = MagicMock()
    ontology.list_entity_types = AsyncMock(
        return_value=[
            SimpleNamespace(code="person", label="人员", property_schema={}),
        ]
    )
    ontology.list_relation_types = AsyncMock(return_value=[])
    ontology.resolve_or_merge_entity_type = AsyncMock(
        return_value=(SimpleNamespace(code="device", label="设备"), True)
    )
    ontology.create_relation_type = AsyncMock()
    ontology.set_subclass_of = AsyncMock()
    ontology.rebuild_shapes_for_all = AsyncMock(return_value={})
    ontology.get_entity_type = AsyncMock(return_value=None)
    ontology._store = MagicMock()

    async def _run():
        stats = await apply_ontology_candidates(
            ontology,
            entity_types=[
                {
                    "code": "device",
                    "label": "设备",
                    "action": "create",
                    "properties": [],
                }
            ],
            relation_types=[
                {
                    "code": "owns",
                    "label": "拥有",
                    "action": "create",
                    "domain_types": ["person"],
                    "range_types": ["device"],
                }
            ],
        )
        assert stats["entity_types_created"] == 1
        assert stats["relation_types_created"] == 1
        ontology.resolve_or_merge_entity_type.assert_called()
        ontology.create_relation_type.assert_called()
        ontology.rebuild_shapes_for_all.assert_awaited()

    asyncio.run(_run())


def test_apply_empty_selection_is_noop():
    ontology = MagicMock()
    ontology.list_entity_types = AsyncMock(return_value=[])
    ontology.list_relation_types = AsyncMock(return_value=[])
    ontology.rebuild_shapes_for_all = AsyncMock()

    async def _run():
        stats = await apply_ontology_candidates(
            ontology, entity_types=[], relation_types=[]
        )
        assert stats["entity_types_created"] == 0
        assert stats["relation_types_created"] == 0
        ontology.rebuild_shapes_for_all.assert_not_called()

    asyncio.run(_run())


def test_discover_and_merge_auto_applies():
    ontology = MagicMock()

    async def _run():
        with (
            patch(
                "app.services.ontology_extraction_service.discover_ontology_candidates",
                new=AsyncMock(
                    return_value={
                        "entity_types": [
                            {
                                "code": "device",
                                "label": "设备",
                                "action": "create",
                                "selected": True,
                                "properties": [],
                            }
                        ],
                        "relation_types": [],
                        "skipped": [],
                        "stats": {"candidates": 1},
                    }
                ),
            ),
            patch(
                "app.services.ontology_extraction_service.apply_ontology_candidates",
                new=AsyncMock(
                    return_value={
                        "entity_types_created": 1,
                        "relation_types_created": 0,
                        "entity_types_merged": 0,
                        "skipped": 0,
                    }
                ),
            ) as apply_mock,
        ):
            stats = await discover_and_merge_ontology(
                ontology, title="t", text="x" * 80
            )
        assert stats["entity_types_created"] == 1
        assert stats["candidates"] == 1
        apply_mock.assert_awaited()

    asyncio.run(_run())
