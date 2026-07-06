# pip install agentkit-mcp
"""演示 MCP 客户端的基本用法：列出工具、调用工具。"""

import asyncio

from agentkit_mcp import McpClient, McpClientConfig


async def main():
    # 配置 MCP 客户端
    config = McpClientConfig(
        endpoint="https://mcp.example.com/mcp",
        client_name="my-app",
        auth_token="optional-bearer-token",
    )
    client = McpClient(config)

    # 列出远程 MCP 工具
    try:
        tools = await client.list_tools()
        print(f"可用工具: {len(tools)}")
        for tool in tools[:3]:
            print(f"  - {tool.get('name')}: {tool.get('description', '')[:60]}")
    except Exception as e:
        print(f"连接失败（预期行为——端点不可达）: {e}")

    # 调用工具（纯文本结果）
    try:
        text = await client.call_tool_text("search", {"query": "最新技术"})
        print("工具返回:", text[:200])
    except Exception as e:
        print(f"调用失败（预期行为——端点不可达）: {e}")


asyncio.run(main())
