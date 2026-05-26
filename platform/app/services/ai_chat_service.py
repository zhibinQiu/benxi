"""AI 首页 — 双碳智能体对话（内置 DeepSeek LLM）。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.core.exceptions import bad_request
from app.integrations.deepseek_client import is_configured, resolve_credentials
from app.schemas.ai_chat import AiChatMessage

_MAX_HISTORY = 20

_SYSTEM_PROMPT = """你是「双碳智能体」，面向企业碳管理、碳核算、碳减排路径、碳市场与 ESG 披露等领域的专业 AI 助手。

你的能力包括：
- 解读双碳政策、标准与行业实践（如碳排放核算边界、范围一/二/三、碳足迹等）
- 协助梳理减排思路、能源结构优化与数据治理建议
- 用清晰、可执行的语言回答，必要时给出分点说明

回答要求：
- 使用简体中文
- 结构清晰，可使用简短 Markdown（标题、列表、加粗）
- 对不确定的数据或政策细节应说明需以最新官方文件为准，勿编造具体数值或文号
- 若问题与双碳主题无关，可简要回应并友好引导回双碳相关话题"""


def _build_chat_messages(*, message: str, history: list[AiChatMessage]) -> list[dict]:
    messages: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT}]
    tail = history[-_MAX_HISTORY:] if history else []
    for item in tail:
        messages.append({"role": item.role, "content": item.content.strip()})
    messages.append({"role": "user", "content": message.strip()})
    return messages


async def iter_chat_with_ai_agent_stream(
    *,
    message: str,
    history: list[AiChatMessage],
) -> AsyncIterator[str]:
    """逐块产出 SSE data 行（不含 event: 前缀，由 API 层包装）。"""
    if not is_configured():
        yield json.dumps({"error": "AI 对话未配置，请联系管理员配置 DeepSeek API"}, ensure_ascii=False)
        return

    messages = _build_chat_messages(message=message, history=history)
    api_key, base_url, model = resolve_credentials()
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.6,
        "stream": True,
    }
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as r:
                if r.status_code >= 400:
                    body = (await r.aread())[:500].decode("utf-8", errors="replace")
                    yield json.dumps(
                        {"error": f"AI 对话暂时不可用: {body}"},
                        ensure_ascii=False,
                    )
                    return
                async for line in r.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                    text = delta.get("content") or ""
                    if text:
                        yield json.dumps({"delta": text}, ensure_ascii=False)
        yield json.dumps({"done": True, "model": model}, ensure_ascii=False)
    except httpx.HTTPError as e:
        yield json.dumps({"error": f"无法连接 AI 服务: {e}"}, ensure_ascii=False)


async def chat_with_ai_agent(
    *,
    message: str,
    history: list[AiChatMessage],
) -> dict:
    if not is_configured():
        raise bad_request("AI 对话未配置，请联系管理员配置 DeepSeek API")

    messages = _build_chat_messages(message=message, history=history)
    api_key, base_url, model = resolve_credentials()
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.6,
    }
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:500] if e.response is not None else str(e)
        raise bad_request(f"AI 对话暂时不可用: {detail}") from e
    except httpx.HTTPError as e:
        raise bad_request(f"无法连接 AI 服务: {e}") from e

    choices = body.get("choices") or []
    if not choices:
        raise bad_request("AI 返回为空")
    reply = (choices[0].get("message", {}) or {}).get("content") or ""
    reply = reply.strip()
    if not reply:
        raise bad_request("AI 返回为空")
    return {"reply": reply, "model": model}
