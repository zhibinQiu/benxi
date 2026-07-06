"""MCP 协议与平台 MCP Server 单元测试。"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.mcp.platform_server import (
    _parse_platform_tool_name,
    handle_mcp_jsonrpc,
    resolve_mcp_service_endpoint,
)
from app.core.mcp.protocol import (
    MCP_PROTOCOL_VERSION,
    build_jsonrpc_request,
    mcp_text_content,
    parse_jsonrpc_response,
    summarize_mcp_tool_result,
)
from app.database import SessionLocal
from app.models.org import User


def test_parse_jsonrpc_response_from_json():
    body = '{"jsonrpc":"2.0","id":1,"result":{"tools":[]}}'
    parsed = parse_jsonrpc_response(body)
    assert parsed["result"]["tools"] == []


def test_parse_jsonrpc_response_from_sse():
    body = 'event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{"ok":true}}\n\n'
    parsed = parse_jsonrpc_response(body)
    assert parsed["result"]["ok"] is True


def test_parse_platform_tool_name():
    assert _parse_platform_tool_name("web-search.search") == ("web-search", "search")
    assert _parse_platform_tool_name("invalid") is None


def test_summarize_mcp_tool_result():
    text = summarize_mcp_tool_result(
        {"content": [{"type": "text", "text": "hello"}]}
    )
    assert text == "hello"


def test_mcp_text_content():
    payload = mcp_text_content("ok")
    assert payload["content"][0]["text"] == "ok"


def test_handle_mcp_initialize_and_tools_list():
    async def _run():
        db = SessionLocal()
        try:
            user = db.scalar(select(User).limit(1))
            assert user is not None
            response, session_id = await handle_mcp_jsonrpc(
                db,
                user,
                build_jsonrpc_request("init-1", "initialize", {}),
            )
            assert response["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION
            assert session_id
            tools_resp, _ = await handle_mcp_jsonrpc(
                db,
                user,
                build_jsonrpc_request("tools-1", "tools/list", {}),
                session_id=session_id,
            )
            tools = tools_resp["result"]["tools"]
            assert isinstance(tools, list)
        finally:
            db.close()

    asyncio.run(_run())


def test_resolve_mcp_service_endpoint(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "mcp_service_base_url", "https://example.com/mcp")
    assert resolve_mcp_service_endpoint() == "https://example.com/mcp"


def test_mcp_info_endpoint(client):
    r = client.get("/api/v1/mcp/info")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["enabled"] is True
    assert data["protocol_version"]
