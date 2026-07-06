"""agentkit-mcp 协议层单元测试。"""

from agentkit_mcp.protocol import (
    build_jsonrpc_request,
    mcp_text_content,
    parse_jsonrpc_response,
    summarize_mcp_tool_result,
)


def test_build_jsonrpc_request():
    req = build_jsonrpc_request("abc", "tools/list", {})
    assert req["jsonrpc"] == "2.0"
    assert req["method"] == "tools/list"
    assert req["id"] == "abc"


def test_parse_json_body():
    body = '{"jsonrpc":"2.0","id":1,"result":{"tools":[]}}'
    parsed = parse_jsonrpc_response(body)
    assert parsed["result"]["tools"] == []


def test_parse_sse_body():
    body = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n'
    parsed = parse_jsonrpc_response(body)
    assert parsed["result"]["ok"] is True


def test_summarize_mcp_tool_result():
    result = {"content": [{"type": "text", "text": "hello world"}]}
    assert summarize_mcp_tool_result(result) == "hello world"


def test_mcp_text_content_error_flag():
    payload = mcp_text_content("fail", is_error=True)
    assert payload["isError"] is True
