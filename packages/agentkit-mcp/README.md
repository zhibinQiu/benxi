# agentkit-mcp

轻量 **MCP（Model Context Protocol）** JSON-RPC 协议与 HTTP/SSE 客户端。

## 特点

- **零平台耦合**：不依赖 FastAPI、SQLAlchemy 或本项目配置
- **节约 token**：`summarize_mcp_tool_result()` 将工具结果压缩为短文本
- **可测试**：协议层纯函数，无需网络即可单测

## 安装

```bash
pip install agentkit-mcp
# 本地开发
pip install -e packages/agentkit-mcp
```

## 快速开始

```python
from agentkit_mcp import McpClient, McpClientConfig

client = McpClient(McpClientConfig(
    endpoint="https://mcp.example.com/mcp",
    client_name="my-app",
    client_version="1.0.0",
    auth_token="optional-bearer-token",
))

tools = await client.list_tools()
text = await client.call_tool_text("search", {"query": "最新政策"})
```

## 仅使用协议层（自定义传输）

```python
from agentkit_mcp.protocol import build_jsonrpc_request, parse_jsonrpc_response

req = build_jsonrpc_request("1", "tools/list", {})
# ... 自行 POST req ...
resp = parse_jsonrpc_response(response_text)
```

## 更多示例

见 [examples/mcp_client.py](../examples/mcp_client.py)
