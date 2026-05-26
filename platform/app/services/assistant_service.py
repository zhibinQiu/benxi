"""智能客服 — 基于平台知识库与 DeepSeek。"""

from __future__ import annotations

import httpx
from sqlalchemy.orm import Session

from app.core.exceptions import bad_request
from app.integrations.deepseek_client import is_configured, resolve_credentials
from app.models.org import User
from app.schemas.assistant import AssistantChatMessage
from app.services.assistant_knowledge import build_platform_knowledge

_MAX_HISTORY = 10


async def chat_with_assistant(
    db: Session,
    user: User,
    *,
    message: str,
    history: list[AssistantChatMessage],
    page_hint: str | None = None,
) -> dict:
    if not is_configured():
        raise bad_request("智能客服未配置，请联系管理员配置 DeepSeek API")

    knowledge = build_platform_knowledge(db, user, page_hint=page_hint)
    system = (
        "你是「智碳平台AI子系统」内置智能客服助手，专门帮助用户理解和使用本平台。\n\n"
        "【平台知识库】\n"
        f"{knowledge}\n\n"
        "请严格依据知识库回答。若问题超出平台使用范围，礼貌说明并建议联系系统管理员。"
        "回答使用简体中文，结构清晰，可使用简短 Markdown。"
    )

    messages: list[dict] = [{"role": "system", "content": system}]
    tail = history[-_MAX_HISTORY:] if history else []
    for item in tail:
        messages.append({"role": item.role, "content": item.content.strip()})
    messages.append({"role": "user", "content": message.strip()})

    api_key, base_url, model = resolve_credentials()
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.35,
    }
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0)) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:500] if e.response is not None else str(e)
        raise bad_request(f"智能客服暂时不可用: {detail}") from e
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
