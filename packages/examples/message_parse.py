"""agentkit-message 使用示例：内嵌工具调用提取、内容过滤、追问检测。

DSML 格式说明（DeepSeek 模型常见）：
  - 定界符用两个竖线：``||``（半角）或 ``\uff5c\uff5c``（全角）
  - 后缀紧跟在定界符后：``<|DSML|invoke name="tool_name">``
  - 参数用嵌套 DSML 块：``<|DSML|parameter name="key">value</|DSML|parameter>``
"""

from agentkit_message import (
    DsmlStreamFilter,
    ContentFilter,
    extract_embedded_tool_calls,
    normalize_assistant_message,
    sanitize_agent_reply,
)
from agentkit_message.context import (
    format_conversation_snippet,
    is_likely_follow_up,
    trim_chat_history,
)


# ── 1. 提取内嵌工具调用 ──────────────────────────────────────────────────────

def demo_extract_tool_calls():
    """LLM 正文中内嵌 DSML 工具调用 → 提取 + 剥离"""
    content = (
        '让我帮你查一下天气。'
        '<|DSML|invoke name="web_search">'
        '<|DSML|parameter name="query">北京天气</|DSML|parameter>'
        '</|DSML|invoke>'
        '请稍等...'
    )

    clean, tool_calls = extract_embedded_tool_calls(content)
    print(f"清理后正文: {clean!r}")
    print(f"提取到 {len(tool_calls)} 个工具调用:")
    for tc in tool_calls:
        print(f"  id={tc['id'][:8]}... name={tc['function']['name']}")
        print(f"  参数: {tc['function']['arguments']}")
    print()


# ── 2. 消息归一化 ────────────────────────────────────────────────────────────

def demo_normalize_message():
    """将 content 中内嵌调用提升到 tool_calls"""
    raw_msg = {
        "role": "assistant",
        "content": (
            '<|DSML|invoke name="knowledge_retrieve">'
            '<|DSML|parameter name="query">公司制度</|DSML|parameter>'
            '</|DSML|invoke>'
        ),
    }
    normalized = normalize_assistant_message(raw_msg)
    print(f"归一化后 tool_calls 数: {len(normalized.get('tool_calls', []))}")
    print(f"归一化后 content 为空: {normalized['content'] == ''}")
    print()


# ── 3. 流式过滤 ──────────────────────────────────────────────────────────────

def demo_stream_filter():
    """实时过滤流式输出中的 DSML 标记"""
    filter = DsmlStreamFilter()

    chunks = [
        "正在查询天",
        '气<|DSML|invoke name="web_search">'
        '<|DSML|parameter name="query">北京</|DSML|parameter>'
        '</|DSML|invoke>',
        "当前温度 25°C",
    ]

    for chunk in chunks:
        clean = filter.feed(chunk)
        if clean:
            print(f"提交: {clean!r}")

    final = filter.flush()
    if final:
        print(f"最终: {final!r}")
    print()


# ── 4. 内容过滤 ──────────────────────────────────────────────────────────────

def demo_content_filter():
    """过滤内部调试内容，保留用户可见交付"""
    filter = ContentFilter()

    internal_text = "已调用 re.search 匹配 pattern，`update_uploaded_skill_file` 执行成功"
    print(f"内部内容判定: {filter.is_internal(internal_text)}")

    deliverable = "这是最终的调研报告摘要：AI 技术在 2024 年快速发展...\n```mermaid\nflowchart LR\nA-->B\n```"
    print(f"可交付判定: {filter.is_deliverable(deliverable)}")

    sanitized = sanitize_agent_reply("让我查一下...\n```python\nprint('test')\n```\n这是结果摘要")
    print(f"净化后文本: {sanitized!r}")
    print()


# ── 5. 追问检测 ──────────────────────────────────────────────────────────────

def demo_follow_up_detection():
    """多轮对话中判断当前输入是否为追问"""
    history = [
        {"role": "user", "content": "帮我查一下北京明天天气"},
        {"role": "assistant", "content": "北京明天晴，25-32°C"},
    ]

    follow_ups = ["那上海呢", "继续", "你好", "详细说说气温"]
    for msg in follow_ups:
        result = is_likely_follow_up(msg, history)
        print(f"  '{msg}' → {'追问' if result else '新话题/寒暄'}")

    # 历史裁剪
    long_history = [{"role": "user", "content": f"消息 {i}"} for i in range(20)]
    trimmed = trim_chat_history(long_history, max_messages=5, max_chars=1000)
    print(f"\n裁剪后: {len(trimmed)} 条 (原始 20 条)")

    # 对话摘要
    snippet = format_conversation_snippet(
        history,
        role_labels={"user": "用户", "assistant": "助手"},
    )
    print(f"对话摘要:\n{snippet}")


if __name__ == "__main__":
    demo_extract_tool_calls()
    demo_normalize_message()
    demo_stream_filter()
    demo_content_filter()
    demo_follow_up_detection()
