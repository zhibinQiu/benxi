# agentkit-message

LLM 消息解析、内嵌工具调用提取、内容过滤 — Agent 消息层面通用处理。

## 安装

```bash
pip install agentkit-message

# 本地开发
pip install -e packages/agentkit-message
```

## 模块概览

| 模块 | 职责 |
|------|------|
| `parse` | 从 LLM 正文中提取 DSML/内嵌式工具调用 |
| `filter` | 过滤内部调试模式，净化面向用户的回复 |
| `context` | 多轮对话上下文分析：追问检测、历史裁剪 |

## 快速开始

```python
from agentkit_message import (
    extract_embedded_tool_calls,
    strip_tool_markup,
    DsmlStreamFilter,
)

# 提取正文中的工具调用
text = '帮我查天气<|DSML|>invoke name="web_search"<|DSML|>parameter name="query">天气</|DSML|>parameter></|DSML|>invoke>'
clean, tool_calls = extract_embedded_tool_calls(text)
assert len(tool_calls) == 1
assert tool_calls[0]["function"]["name"] == "web_search"

# 流式过滤
filter = DsmlStreamFilter()
clean_chunk = filter.feed(text)
final = filter.flush()
```

```python
from agentkit_message.context import (
    is_likely_follow_up,
    trim_chat_history,
    format_conversation_snippet,
)

# 判断是否为追问
assert is_likely_follow_up("继续", history)

# 裁剪历史
trimmed = trim_chat_history(history, max_messages=8, max_chars=6000)
```
