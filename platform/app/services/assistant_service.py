"""智能客服 — 基于平台知识库与 DeepSeek。"""

from __future__ import annotations

import httpx
from sqlalchemy.orm import Session

from app.core.exceptions import bad_request
from app.core.prompt_budget import build_bounded_chat_messages, llm_completion_extras
from app.core.platform_assistant import assistant_support_persona, assistant_user_communication_style
from app.integrations.deepseek_client import is_configured, resolve_credentials
from app.models.org import User
from app.schemas.assistant import AssistantChatMessage
from app.services import platform_chat_store
from app.services.assistant_knowledge import build_platform_knowledge


async def chat_with_assistant(
    db: Session,
    user: User,
    *,
    message: str,
    history: list[AssistantChatMessage],
    page_hint: str | None = None,
    conversation_id: str | None = None,
) -> dict:
    if not is_configured():
        raise bad_request("本析平台客服未配置，请联系管理员配置 DeepSeek API")

    knowledge = build_platform_knowledge(db, user, page_hint=page_hint)
    messages = build_bounded_chat_messages(
        system=(
            f"{assistant_support_persona()}。\n\n"
            "【平台知识库】\n"
            f"{knowledge}\n\n"
            "请严格依据知识库回答。若问题超出平台使用范围，礼貌说明并建议联系系统管理员。"
            "提及助手时统一自称「小析」。\n"
            f"{assistant_user_communication_style()}"
        ),
        history=history,
        user_message=message,
    )

    api_key, base_url, model = resolve_credentials()
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.35,
        **llm_completion_extras(),
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
        raise bad_request(f"本析平台客服暂时不可用: {detail}") from e
    except httpx.HTTPError as e:
        raise bad_request(f"无法连接 AI 服务: {e}") from e

    choices = body.get("choices") or []
    if not choices:
        raise bad_request("AI 返回为空")
    reply = (choices[0].get("message", {}) or {}).get("content") or ""
    reply = reply.strip()
    if not reply:
        raise bad_request("AI 返回为空")

    conv = platform_chat_store.get_or_create_conversation(
        db,
        user_id=user.id,
        scope="assistant",
        conversation_id=conversation_id,
    )
    platform_chat_store.append_turn(
        db,
        conversation=conv,
        user_message=message,
        assistant_message=reply,
    )
    db.commit()
    return {"reply": reply, "model": model, "conversation_id": str(conv.id)}
