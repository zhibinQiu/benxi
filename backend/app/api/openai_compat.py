"""本析智能 OpenAI 兼容对外 API（chat/completions、models）。

流式 delta 约定（与 DeepSeek / vLLM 等兼容习惯对齐）：
- ``choices[0].delta.reasoning_content`` / ``reasoning``：思考与执行过程
- ``choices[0].delta.content``：最终正文
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse, StreamingResponse

from app.agent.aip.auth import is_aip_sk_token
from app.api.deps import _resolve_token, get_client_ip
from app.core.agent_api_mode import agent_api_mode
from app.core.async_db import StreamCapacityError, detach_request_db, stream_db_slot
from app.core.exceptions import AppError, forbidden, unauthorized
from app.core.user_messages import KNOWLEDGE_SERVICE_UNAVAILABLE, sanitize_user_message
from app.database import get_db
from app.schemas.ai_chat import AiChatMessage
from app.schemas.ai_home_openai import OpenAiChatCompletionRequest
from app.services import ai_home_api_settings_service as settings_svc
from app.services.ai_chat_service import iter_chat_with_ai_agent_stream
from app.services.aip_secret_key_service import authenticate_secret_key
from app.services.audit_service import write_audit

router = APIRouter(prefix="/openai/v1", tags=["openai-compat"])
_bearer = HTTPBearer(auto_error=False)

_DEFAULT_MODEL = "benxi"
_SUPPORTED_MODELS = frozenset({"benxi", "benxi-ai", "grm"})
_DIRECT_LLM_MODEL = "grm"

# 映射到 reasoning 的 workflow phase（排除纯 UI 噪声）
_REASONING_PHASES = frozenset(
    {
        "workflow_started",
        "thinking_delta",
        "agent_thinking",
        "llm_thinking",
        "agent_thought",
        "llm_decision",
        "agent_plan",
        "plan_tasks",
        "task_started",
        "task_retry",
        "task_done",
        "task_failed",
        "tool_call",
        "tool_result",
        "url_parse_progress",
        "orchestrator_progress",
    }
)


def _resolve_model(raw: str | None) -> str:
    """校验并规范化 model：benxi=完整 Agent；grm=直连默认语言模型。"""
    model = (raw or _DEFAULT_MODEL).strip() or _DEFAULT_MODEL
    # 兼容第三方把上游真实模型名填进来的情况
    if model not in _SUPPORTED_MODELS:
        lowered = model.lower()
        if lowered == "grm" or lowered.startswith("grm-"):
            return _DIRECT_LLM_MODEL
        raise AppError(
            404,
            f"The model `{model}` does not exist. Use `benxi` (Agent) or `grm` (default LLM).",
            status_code=404,
        )
    return model


def _openai_error(status_code: int, message: str, *, err_type: str = "invalid_request_error") -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"message": message, "type": err_type, "code": status_code}},
    )


def _require_sk_user(
    request: Request,
    db: Session,
    creds: HTTPAuthorizationCredentials | None,
):
    token = _resolve_token(request, creds)
    if not is_aip_sk_token(token):
        raise unauthorized("需要 AIP 密钥（Authorization: Bearer sk-aip-…）")
    return authenticate_secret_key(db, token.strip())


def _require_openai_api_enabled(db: Session) -> None:
    if not settings_svc.is_openai_api_enabled(db):
        raise forbidden("本析智能 OpenAPI 未开放，请在多智能体中为「小析」开启「服务开放」")


def _message_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
                elif "text" in item:
                    parts.append(str(item.get("text") or ""))
        return "\n".join(p for p in parts if p).strip()
    return str(content).strip()


def _map_messages(
    messages: list[Any],
) -> tuple[str, list[AiChatMessage]]:
    """将 OpenAI messages 映射为本析智能 message + history。"""
    history: list[AiChatMessage] = []
    last_user = ""
    for msg in messages:
        role = str(getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else "")).strip()
        content = _message_text(
            getattr(msg, "content", None)
            if not isinstance(msg, dict)
            else msg.get("content")
        )
        if not content:
            continue
        if role == "user":
            if last_user:
                history.append(AiChatMessage(role="user", content=last_user[:16000]))
            last_user = content
        elif role == "assistant":
            if last_user:
                history.append(AiChatMessage(role="user", content=last_user[:16000]))
                last_user = ""
            history.append(AiChatMessage(role="assistant", content=content[:16000]))
        # system / tool / 其它角色忽略（Agent 自有 system prompt）
    if not last_user:
        raise AppError(400, "messages 中需要至少一条 user 消息", status_code=400)
    if len(history) > 40:
        history = history[-40:]
    return last_user[:8000], history


def _map_messages_for_llm(messages: list[Any]) -> list[dict[str, str]]:
    """直连 LLM：保留 system / user / assistant。"""
    systems: list[dict[str, str]] = []
    turns: list[dict[str, str]] = []
    has_user = False
    for msg in messages:
        role = str(
            getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else "")
        ).strip()
        if role not in ("system", "user", "assistant"):
            continue
        content = _message_text(
            getattr(msg, "content", None)
            if not isinstance(msg, dict)
            else msg.get("content")
        )
        if not content:
            continue
        row = {"role": role, "content": content[:16000]}
        if role == "system":
            systems.append(row)
        else:
            if role == "user":
                has_user = True
            turns.append(row)
    if not has_user:
        raise AppError(400, "messages 中需要至少一条 user 消息", status_code=400)
    return systems[:3] + turns[-40:]


def _completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


def _reasoning_from_workflow(wf: dict[str, Any]) -> str:
    """将平台 workflow 事件转为 OpenAI reasoning 增量（标准 stage 前缀）。"""
    from app.agent.orchestrate.protocol import format_reasoning_line

    phase = str(wf.get("phase") or "").strip()
    if phase not in _REASONING_PHASES and not wf.get("stage"):
        return ""
    return format_reasoning_line(wf)


@dataclass
class _MappedDelta:
    content: str | None = None
    reasoning: str | None = None
    finish: bool = False
    error: str | None = None


@dataclass
class _OpenAiEventMapper:
    """平台 SSE → OpenAI delta（content / reasoning）增量映射。"""

    content_acc: str = ""
    had_content: bool = False

    def feed(self, data: dict[str, Any]) -> list[_MappedDelta]:
        if data.get("error"):
            return [
                _MappedDelta(
                    error=str(data.get("error") or KNOWLEDGE_SERVICE_UNAVAILABLE)
                )
            ]

        out: list[_MappedDelta] = []

        wf = data.get("workflow")
        if isinstance(wf, dict):
            reasoning = _reasoning_from_workflow(wf)
            if reasoning:
                out.append(_MappedDelta(reasoning=reasoning))

        delta_text = data.get("delta")
        if isinstance(delta_text, str) and delta_text:
            self.content_acc += delta_text
            self.had_content = True
            out.append(_MappedDelta(content=delta_text))

        replace_text = data.get("replace")
        if isinstance(replace_text, str) and replace_text:
            # replace 为全量快照：只下发相对已推送正文的后缀，避免客户端累加重复
            if replace_text.startswith(self.content_acc):
                suffix = replace_text[len(self.content_acc) :]
                if suffix:
                    self.content_acc = replace_text
                    self.had_content = True
                    out.append(_MappedDelta(content=suffix))
            elif not self.content_acc:
                self.content_acc = replace_text
                self.had_content = True
                out.append(_MappedDelta(content=replace_text))
            # 已有正文且终稿不一致：跳过，避免把整篇再追加一遍

        if data.get("done"):
            reply = data.get("reply")
            if (
                isinstance(reply, str)
                and reply
                and not self.had_content
            ):
                self.content_acc = reply
                self.had_content = True
                out.append(_MappedDelta(content=reply))
            out.append(_MappedDelta(finish=True))

        return out


def _non_stream_response(
    *,
    completion_id: str,
    model: str,
    content: str,
    reasoning: str = "",
) -> dict[str, Any]:
    created = int(time.time())
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if reasoning:
        # DeepSeek 系 reasoning_content；vLLM / Together 系 reasoning
        message["reasoning_content"] = reasoning
        message["reasoning"] = reasoning
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": model or _DEFAULT_MODEL,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _chunk_payload(
    *,
    completion_id: str,
    model: str,
    content: str | None = None,
    reasoning: str | None = None,
    role: str | None = None,
    finish_reason: str | None = None,
) -> str:
    delta: dict[str, Any] = {}
    if role is not None:
        delta["role"] = role
    if content is not None:
        delta["content"] = content
    if reasoning is not None:
        delta["reasoning_content"] = reasoning
        delta["reasoning"] = reasoning
    payload = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model or _DEFAULT_MODEL,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def _sse_data(payload: str) -> str:
    return f"data: {payload}\n\n"


async def _iter_agent_mapped_events(
    *,
    user_id: uuid.UUID,
    message: str,
    history: list[AiChatMessage],
) -> AsyncIterator[_MappedDelta]:
    mapper = _OpenAiEventMapper()
    with agent_api_mode(True):
        async for payload in iter_chat_with_ai_agent_stream(
            user_id=user_id,
            message=message,
            history=history,
        ):
            try:
                data = json.loads(payload) if isinstance(payload, str) else payload
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(data, dict):
                continue
            for piece in mapper.feed(data):
                yield piece


async def _iter_openai_sse(
    *,
    user_id: uuid.UUID,
    message: str,
    history: list[AiChatMessage],
    model: str,
    completion_id: str,
) -> AsyncIterator[str]:
    yielded_role = False
    finished = False
    async for piece in _iter_agent_mapped_events(
        user_id=user_id,
        message=message,
        history=history,
    ):
        if piece.error:
            yield _sse_data(
                json.dumps(
                    {"error": {"message": piece.error, "type": "server_error"}},
                    ensure_ascii=False,
                )
            )
            yield _sse_data("[DONE]")
            return
        if piece.reasoning or piece.content is not None:
            if not yielded_role:
                yield _sse_data(
                    _chunk_payload(
                        completion_id=completion_id,
                        model=model,
                        role="assistant",
                        content="",
                    )
                )
                yielded_role = True
            yield _sse_data(
                _chunk_payload(
                    completion_id=completion_id,
                    model=model,
                    content=piece.content,
                    reasoning=piece.reasoning,
                )
            )
        if piece.finish:
            if not yielded_role:
                yield _sse_data(
                    _chunk_payload(
                        completion_id=completion_id,
                        model=model,
                        role="assistant",
                        content="",
                    )
                )
                yielded_role = True
            yield _sse_data(
                _chunk_payload(
                    completion_id=completion_id,
                    model=model,
                    finish_reason="stop",
                )
            )
            yield _sse_data("[DONE]")
            finished = True
            return
    if not finished:
        if not yielded_role:
            yield _sse_data(
                _chunk_payload(
                    completion_id=completion_id,
                    model=model,
                    role="assistant",
                    content="",
                )
            )
        yield _sse_data(
            _chunk_payload(
                completion_id=completion_id,
                model=model,
                finish_reason="stop",
            )
        )
        yield _sse_data("[DONE]")


async def _collect_openai_completion(
    *,
    user_id: uuid.UUID,
    message: str,
    history: list[AiChatMessage],
) -> tuple[str, str]:
    """非流式：复用同一映射，收集 content + reasoning。"""
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    async for piece in _iter_agent_mapped_events(
        user_id=user_id,
        message=message,
        history=history,
    ):
        if piece.error:
            raise AppError(500, piece.error, status_code=500)
        if piece.reasoning:
            reasoning_parts.append(piece.reasoning)
        if piece.content:
            content_parts.append(piece.content)
    return "".join(content_parts), "".join(reasoning_parts)


def _delta_reasoning_text(delta: dict[str, Any]) -> str:
    for key in ("reasoning_content", "reasoning"):
        val = delta.get(key)
        if isinstance(val, str) and val:
            return val
    return ""


async def _iter_grm_sse(
    *,
    messages: list[dict[str, str]],
    model: str,
    completion_id: str,
    temperature: float | None,
    max_tokens: int | None,
) -> AsyncIterator[str]:
    """直连平台默认语言模型，透传 content / reasoning。"""
    import httpx

    from app.integrations.deepseek_client import (
        _chat_url,
        format_llm_stream_error,
        resolve_credentials,
    )

    try:
        api_key, base_url, upstream_model = resolve_credentials()
    except Exception as exc:
        yield _sse_data(
            json.dumps(
                {"error": {"message": str(exc), "type": "server_error"}},
                ensure_ascii=False,
            )
        )
        yield _sse_data("[DONE]")
        return

    payload: dict[str, Any] = {
        "model": upstream_model,
        "messages": messages,
        "stream": True,
        "temperature": 0.3 if temperature is None else float(temperature),
    }
    if max_tokens is not None and int(max_tokens) > 0:
        payload["max_tokens"] = int(max_tokens)

    yielded_role = False
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream(
                "POST",
                _chat_url(base_url),
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            ) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", errors="replace")[:300]
                    if resp.status_code == 401:
                        msg = "语言模型 API 密钥无效，请检查「资源管理 → 模型」"
                    elif resp.status_code == 404:
                        msg = "语言模型接口不存在，请确认 Base URL 含 /v1"
                    else:
                        msg = f"语言模型调用失败（HTTP {resp.status_code}）"
                    if body:
                        msg = f"{msg}: {body}"
                    yield _sse_data(
                        json.dumps(
                            {"error": {"message": msg, "type": "server_error"}},
                            ensure_ascii=False,
                        )
                    )
                    yield _sse_data("[DONE]")
                    return
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw:
                        continue
                    if raw == "[DONE]":
                        break
                    try:
                        chunk = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    reasoning = _delta_reasoning_text(delta)
                    finish = choices[0].get("finish_reason")
                    if not yielded_role and (
                        content is not None or reasoning or delta.get("role") or finish
                    ):
                        yield _sse_data(
                            _chunk_payload(
                                completion_id=completion_id,
                                model=model,
                                role="assistant",
                                content="",
                            )
                        )
                        yielded_role = True
                    if (isinstance(content, str) and content) or reasoning:
                        yield _sse_data(
                            _chunk_payload(
                                completion_id=completion_id,
                                model=model,
                                content=content if isinstance(content, str) and content else None,
                                reasoning=reasoning or None,
                            )
                        )
                    if finish:
                        yield _sse_data(
                            _chunk_payload(
                                completion_id=completion_id,
                                model=model,
                                finish_reason=str(finish),
                            )
                        )
                        yield _sse_data("[DONE]")
                        return
    except Exception as exc:
        yield _sse_data(
            json.dumps(
                {
                    "error": {
                        "message": format_llm_stream_error(exc),
                        "type": "server_error",
                    }
                },
                ensure_ascii=False,
            )
        )
        yield _sse_data("[DONE]")
        return

    if not yielded_role:
        yield _sse_data(
            _chunk_payload(
                completion_id=completion_id,
                model=model,
                role="assistant",
                content="",
            )
        )
    yield _sse_data(
        _chunk_payload(
            completion_id=completion_id,
            model=model,
            finish_reason="stop",
        )
    )
    yield _sse_data("[DONE]")


async def _grm_non_stream(
    *,
    messages: list[dict[str, str]],
    temperature: float | None,
    max_tokens: int | None,
) -> tuple[str, str]:
    """直连默认 LLM 非流式，返回 (content, reasoning)。"""
    import httpx

    from app.integrations.deepseek_client import (
        _chat_url,
        format_llm_stream_error,
        resolve_credentials,
    )

    api_key, base_url, upstream_model = resolve_credentials()
    payload: dict[str, Any] = {
        "model": upstream_model,
        "messages": messages,
        "temperature": 0.3 if temperature is None else float(temperature),
    }
    if max_tokens is not None and int(max_tokens) > 0:
        payload["max_tokens"] = int(max_tokens)
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                _chat_url(base_url),
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        raise AppError(502, format_llm_stream_error(exc), status_code=502) from exc

    choices = data.get("choices") or []
    if not choices:
        raise AppError(502, "语言模型未返回有效响应", status_code=502)
    message = choices[0].get("message") or {}
    content = str(message.get("content") or "")
    reasoning = ""
    for key in ("reasoning_content", "reasoning"):
        val = message.get(key)
        if isinstance(val, str) and val.strip():
            reasoning = val
            break
    return content, reasoning


@router.get("/models")
def list_models(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> JSONResponse:
    try:
        _require_openai_api_enabled(db)
        _require_sk_user(request, db, creds)
    except AppError as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        return _openai_error(
            exc.status_code,
            str(detail.get("message") or "请求失败"),
            err_type="authentication_error" if exc.status_code == 401 else "invalid_request_error",
        )
    created = int(time.time())
    return JSONResponse(
        content={
            "object": "list",
            "data": [
                {
                    "id": model_id,
                    "object": "model",
                    "created": created,
                    "owned_by": "benxi",
                }
                for model_id in sorted(_SUPPORTED_MODELS)
            ],
        }
    )


@router.post("/chat/completions")
async def chat_completions(
    body: OpenAiChatCompletionRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    client_ip: Annotated[str | None, Depends(get_client_ip)] = None,
):
    try:
        _require_openai_api_enabled(db)
        sk_row, user = _require_sk_user(request, db, creds)
        model = _resolve_model(body.model)
        if model == _DIRECT_LLM_MODEL:
            llm_messages = _map_messages_for_llm(body.messages)
            message, history = "", []
        else:
            llm_messages = []
            message, history = _map_messages(body.messages)
    except AppError as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        err_type = "authentication_error" if exc.status_code == 401 else "invalid_request_error"
        if exc.status_code == 404:
            err_type = "invalid_request_error"
        return _openai_error(
            exc.status_code,
            str(detail.get("message") or "请求失败"),
            err_type=err_type,
        )

    completion_id = _completion_id()
    user_id = user.id
    write_audit(
        db,
        user_id=user_id,
        action="ai_home.openai.chat",
        resource_type="ai_home_openai",
        detail={
            "sk_id": str(sk_row.id),
            "stream": bool(body.stream),
            "model": model,
            "mode": "llm" if model == _DIRECT_LLM_MODEL else "agent",
        },
        ip_address=client_ip,
    )

    if model == _DIRECT_LLM_MODEL:
        if body.stream:
            detach_request_db(db)

            async def _grm_stream() -> AsyncIterator[str]:
                try:
                    async for line in _iter_grm_sse(
                        messages=llm_messages,
                        model=model,
                        completion_id=completion_id,
                        temperature=body.temperature,
                        max_tokens=body.max_tokens,
                    ):
                        yield line
                except Exception as exc:
                    msg = sanitize_user_message(
                        str(exc), fallback=KNOWLEDGE_SERVICE_UNAVAILABLE
                    )
                    yield _sse_data(
                        json.dumps(
                            {"error": {"message": msg, "type": "server_error"}},
                            ensure_ascii=False,
                        )
                    )
                    yield _sse_data("[DONE]")

            return StreamingResponse(
                _grm_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        try:
            content, reasoning = await _grm_non_stream(
                messages=llm_messages,
                temperature=body.temperature,
                max_tokens=body.max_tokens,
            )
        except AppError as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            return _openai_error(
                exc.status_code,
                str(detail.get("message") or "请求失败"),
                err_type="server_error",
            )
        except Exception as exc:
            msg = sanitize_user_message(str(exc), fallback=KNOWLEDGE_SERVICE_UNAVAILABLE)
            return _openai_error(500, msg, err_type="server_error")

        return JSONResponse(
            content=_non_stream_response(
                completion_id=completion_id,
                model=model,
                content=content,
                reasoning=reasoning,
            )
        )

    if body.stream:
        detach_request_db(db)

        async def _stream() -> AsyncIterator[str]:
            try:
                async with stream_db_slot():
                    async for line in _iter_openai_sse(
                        user_id=user_id,
                        message=message,
                        history=history,
                        model=model,
                        completion_id=completion_id,
                    ):
                        yield line
            except StreamCapacityError as exc:
                yield _sse_data(
                    json.dumps(
                        {"error": {"message": str(exc), "type": "server_error"}},
                        ensure_ascii=False,
                    )
                )
                yield _sse_data("[DONE]")
            except Exception as exc:
                msg = sanitize_user_message(str(exc), fallback=KNOWLEDGE_SERVICE_UNAVAILABLE)
                yield _sse_data(
                    json.dumps(
                        {"error": {"message": msg, "type": "server_error"}},
                        ensure_ascii=False,
                    )
                )
                yield _sse_data("[DONE]")

        return StreamingResponse(
            _stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    detach_request_db(db)
    try:
        async with stream_db_slot():
            content, reasoning = await _collect_openai_completion(
                user_id=user_id,
                message=message,
                history=history,
            )
    except StreamCapacityError as exc:
        return _openai_error(503, str(exc), err_type="server_error")
    except AppError as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        return _openai_error(
            exc.status_code,
            str(detail.get("message") or "请求失败"),
        )
    except Exception as exc:
        msg = sanitize_user_message(str(exc), fallback=KNOWLEDGE_SERVICE_UNAVAILABLE)
        return _openai_error(500, msg, err_type="server_error")

    return JSONResponse(
        content=_non_stream_response(
            completion_id=completion_id,
            model=model,
            content=content,
            reasoning=reasoning,
        )
    )
