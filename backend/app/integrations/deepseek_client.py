"""平台语言模型调用（OpenAI 兼容 chat/completions）— 用于纪要、摘要、问答等。"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import httpx
import tomllib

from app.config import get_settings
from app.core.exceptions import bad_request

_current_provider_id: ContextVar[str | None] = ContextVar("_current_provider_id", default=None)

# ── TTL 缓存：避免同步 DB 调用阻塞事件循环 ──
_CRED_CACHE: dict[str, tuple[float, Any]] = {}
_CRED_CACHE_TTL = 30.0  # 秒


def _cache_get(key: str) -> Any | None:
    entry = _CRED_CACHE.get(key)
    if entry is None:
        return None
    ts, value = entry
    if time.monotonic() - ts > _CRED_CACHE_TTL:
        _CRED_CACHE.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: Any) -> None:
    _CRED_CACHE[key] = (time.monotonic(), value)


def set_current_provider_id(provider_id: str | None) -> None:
    """设置当前请求的 provider_id，供 resolve_credentials 读取。"""
    if provider_id:
        _current_provider_id.set(provider_id)
    else:
        _current_provider_id.set(None)


def get_current_provider_id() -> str | None:
    """获取当前请求的 provider_id。"""
    return _current_provider_id.get()

logger = logging.getLogger(__name__)

STYLE_PROMPTS = {
    "brief": "用 3–5 条要点简要概括，每条一行。",
    "detailed": "分「背景」「讨论要点」「结论与建议」三部分详细总结。",
    "minutes": "按会议纪要格式输出：主题、参会概况（若有）、讨论要点、决议与待办事项。",
}

_PDF2ZH_CONFIG = Path.home() / ".config/pdf2zh/config.v3.toml"


def _clean_key(value: str | None) -> str | None:
    if value is None:
        return None
    v = str(value).strip()
    if not v or v.lower() == "null":
        return None
    return v


def _load_from_pdf2zh_config() -> tuple[str | None, str, str]:
    """从 pdf2zh 配置文件读取密钥（与翻译引擎共用时的兜底）。"""
    if not _PDF2ZH_CONFIG.is_file():
        return None, "https://api.deepseek.com/v1", "deepseek-chat"
    try:
        with _PDF2ZH_CONFIG.open("rb") as f:
            data = tomllib.load(f)
    except Exception:
        return None, "https://api.deepseek.com/v1", "deepseek-chat"
    detail = data.get("deepseek_detail") or {}
    key = _clean_key(detail.get("deepseek_api_key"))
    model = _clean_key(detail.get("deepseek_model")) or "deepseek-chat"
    return key, "https://api.deepseek.com/v1", model


def _platform_llm_credentials() -> tuple[str, str, str]:
    cached = _cache_get("_platform")
    if cached is not None:
        return cached
    from app.database import SessionLocal
    from app.services.model_settings_service import get_llm_credentials

    with SessionLocal() as db:
        result = get_llm_credentials(db)
    _cache_set("_platform", result)
    return result


def resolve_credentials() -> tuple[str, str, str]:
    """返回 (api_key, base_url, model)；优先资源管理中的语言模型配置。

    如果通过 set_current_provider_id() 设置了 provider_id，则使用该 provider 的凭证。
    """
    provider_id = get_current_provider_id()
    if provider_id:
        cache_key = f"provider:{provider_id}"
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
        from app.database import SessionLocal
        from app.services.model_settings_service import get_provider_credentials_by_id

        with SessionLocal() as db:
            result = get_provider_credentials_by_id(provider_id, db)
        if result is not None:
            key, base, model = result
            key_clean = _clean_key(key)
            base_clean = (base or "").strip().rstrip("/")
            model_clean = (model or "").strip()
            if key_clean and base_clean and model_clean:
                creds = (key_clean, base_clean, model_clean)
                _cache_set(cache_key, creds)
                return creds

    base, key, model = _platform_llm_credentials()
    key_clean = _clean_key(key)
    base_clean = (base or "").strip().rstrip("/")
    model_clean = (model or "").strip()

    if not key_clean:
        fk, fb, fm = _load_from_pdf2zh_config()
        if fk:
            return fk, base_clean or fb, model_clean or fm

    if not key_clean:
        raise bad_request("语言模型未配置，请在资源管理中配置 LLM（API URL、模型名与 Key）")

    if not base_clean:
        raise bad_request("语言模型未配置 API 地址，请在资源管理中填写")
    if not model_clean:
        raise bad_request("语言模型未配置模型名，请在资源管理中填写")

    return key_clean, base_clean, model_clean


def is_configured() -> bool:
    try:
        _, _, _ = resolve_credentials()
        return True
    except Exception:
        return False


def _chat_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/chat/completions"


def format_llm_stream_error(exc: Exception) -> str:
    """将 LLM 流式调用异常转为用户可读提示。"""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code if exc.response is not None else 0
        if code == 402:
            return "语言模型账户余额不足或配额已用尽，请联系管理员"
        if code == 401:
            return "语言模型 API 密钥无效，请联系管理员"
        if code == 429:
            return "语言模型请求过于频繁，请稍后重试"
        if code in {502, 503, 504}:
            return "语言模型服务暂不可用，请稍后重试"
        return f"语言模型调用失败（HTTP {code}），请稍后重试"
    if isinstance(exc, httpx.TimeoutException):
        return "语言模型响应超时，请稍后重试"
    if isinstance(exc, httpx.HTTPError):
        return "无法连接语言模型服务，请稍后重试"
    msg = str(exc or "").strip()
    return msg or "语言模型调用失败，请稍后重试"


def _clip_user_content(content: str, max_chars: int | None = None) -> str:
    from app.core.prompt_budget import get_prompt_limits, truncate_to_budget

    limits = get_prompt_limits()
    limit = max_chars if max_chars is not None else limits["user_max_chars"]
    return truncate_to_budget(content or "", limit)


def _prepare_messages_for_api(
    messages: list[dict[str, Any]],
    *,
    max_total_chars: int | None = None,
) -> list[dict[str, Any]]:
    from app.core.prompt_budget import fit_messages_to_total_budget, get_prompt_limits

    limits = get_prompt_limits()
    budget = max_total_chars if max_total_chars is not None else limits["prompt_max_chars"]
    clipped: list[dict[str, Any]] = []
    for msg in messages:
        role = str(msg.get("role") or "user")
        row: dict[str, Any] = {"role": role}
        if msg.get("content") is not None:
            content = str(msg.get("content") or "")
            if role == "user":
                content = _clip_user_content(content)
            row["content"] = content
        if msg.get("tool_calls"):
            row["tool_calls"] = msg["tool_calls"]
        if msg.get("tool_call_id"):
            row["tool_call_id"] = str(msg["tool_call_id"])
        clipped.append(row)
    return fit_messages_to_total_budget(clipped, budget)  # type: ignore[return-value]


async def chat_completion_message_async(
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.3,
    timeout: float = 120.0,
) -> dict[str, Any] | None:
    """单次 chat/completions，返回 choices[0]（含 message.tool_calls）。"""
    from app.core.prompt_budget import llm_completion_extras

    if not is_configured():
        return None
    try:
        api_key, base_url, model = resolve_credentials()
    except Exception as exc:
        logger.warning("LLM 凭据解析失败（非流式）: %s", exc)
        return None
    payload: dict[str, Any] = {
        "model": model,
        "messages": _prepare_messages_for_api(messages),
        "temperature": temperature,
        **llm_completion_extras(),
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                _chat_url(base_url),
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices") or []
            return choices[0] if choices else None
    except Exception as exc:
        logger.warning(
            "LLM tool 调用失败 type=%s repr=%s",
            type(exc).__name__,
            repr(exc)[:200],
        )
        return None


def _completion_payload(
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    stream: bool = False,
    max_total_chars: int | None = None,
    unlimited_output: bool = False,
) -> dict:
    from app.core.prompt_budget import llm_completion_extras

    payload: dict = {
        "model": model,
        "messages": _prepare_messages_for_api(messages, max_total_chars=max_total_chars),
        "temperature": temperature,
        **llm_completion_extras(unlimited=unlimited_output),
    }
    if stream:
        payload["stream"] = True
    return payload


def chat_completion_sync(
    *,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
    timeout: float = 90.0,
    max_user_chars: int | None = None,
) -> str | None:
    """同步 chat/completions；未配置 LLM 或调用失败时返回 None。"""
    if not is_configured():
        return None
    try:
        api_key, base_url, model = resolve_credentials()
    except Exception:
        return None
    payload_messages = _prepare_messages_for_api(messages)
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                _chat_url(base_url),
                headers={"Authorization": f"Bearer {api_key}"},
                json=_completion_payload(
                    model=model,
                    messages=payload_messages,
                    temperature=temperature,
                ),
            )
            resp.raise_for_status()
            data = resp.json()
            return (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            ) or None
    except Exception as exc:
        logger.warning("LLM 同步调用失败: %s", exc)
        return None


async def chat_completion_stream_parts(
    *,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
    timeout: float = 90.0,
    max_user_chars: int | None = None,
    unlimited_output: bool = False,
    max_total_chars: int | None = None,
) -> AsyncIterator[dict[str, str]]:
    """流式 chat/completions；产出 kind=reasoning|content|error 的文本片段。"""
    if not is_configured():
        yield {"kind": "error", "text": "语言模型未配置，请联系管理员"}
        return
    try:
        api_key, base_url, model = resolve_credentials()
    except Exception as exc:
        yield {"kind": "error", "text": format_llm_stream_error(exc)}
        return
    payload_messages = _prepare_messages_for_api(
        messages,
        max_total_chars=max_total_chars,
    )
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                _chat_url(base_url),
                headers={"Authorization": f"Bearer {api_key}"},
                json=_completion_payload(
                    model=model,
                    messages=payload_messages,
                    temperature=temperature,
                    stream=True,
                    max_total_chars=max_total_chars,
                    unlimited_output=unlimited_output,
                ),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        if raw == "[DONE]":
                            break
                        continue
                    try:
                        chunk = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    delta_obj = (chunk.get("choices") or [{}])[0].get("delta") or {}
                    reasoning = delta_obj.get("reasoning_content") or ""
                    content = delta_obj.get("content") or ""
                    if reasoning:
                        yield {"kind": "reasoning", "text": reasoning}
                    if content:
                        yield {"kind": "content", "text": content}
    except Exception as exc:
        logger.warning("LLM 流式调用失败: %s", exc)
        yield {"kind": "error", "text": format_llm_stream_error(exc)}


async def chat_completion_stream(
    *,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
    timeout: float = 90.0,
    max_user_chars: int | None = None,
) -> AsyncIterator[str]:
    """流式 chat/completions；未配置或失败时不产出。"""
    async for part in chat_completion_stream_parts(
        messages=messages,
        temperature=temperature,
        timeout=timeout,
        max_user_chars=max_user_chars,
    ):
        if part.get("kind") == "content" and part.get("text"):
            yield part["text"]


async def chat_completion_stream_choice(
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.3,
    timeout: float = 120.0,
) -> AsyncIterator[dict[str, Any]]:
    """流式 chat/completions（支持 tools），产出两类事件：

    - {"type": "delta", "text": str}  — 内容片段（供 thinking_delta 展示）
    - {"type": "choice", "message": dict, "finish_reason": str}
      — 完整 choice（含 tool_calls），流结束时产出
    """
    from app.core.prompt_budget import llm_completion_extras

    if not is_configured():
        logger.warning("LLM 流式推理调用失败：模型未配置")
        return
    try:
        api_key, base_url, model = resolve_credentials()
    except Exception as exc:
        logger.warning("LLM 凭据解析失败（流式）: %s", exc)
        return
    payload_messages = _prepare_messages_for_api(messages)
    payload: dict[str, Any] = {
        "model": model,
        "messages": payload_messages,
        "temperature": temperature,
        "stream": True,
        **llm_completion_extras(),
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    assistant_message: dict[str, Any] = {"role": "assistant", "content": ""}
    tool_calls_by_index: dict[int, dict[str, Any]] = {}
    finish_reason: str = ""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                _chat_url(base_url),
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        if raw == "[DONE]":
                            break
                        continue
                    try:
                        chunk = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    if delta.get("role"):
                        assistant_message["role"] = delta["role"]
                    tc_deltas = delta.get("tool_calls")
                    if tc_deltas:
                        for tc in tc_deltas:
                            idx = int(tc.get("index", 0))
                            if idx not in tool_calls_by_index:
                                tool_calls_by_index[idx] = {
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                }
                            target = tool_calls_by_index[idx]
                            if tc.get("id"):
                                target["id"] = tc["id"]
                            if tc.get("type"):
                                target["type"] = tc["type"]
                            fn = tc.get("function") or {}
                            if fn.get("name"):
                                target["function"]["name"] = fn["name"]
                            if fn.get("arguments"):
                                target["function"]["arguments"] += fn["arguments"]
                    content = delta.get("content") or ""
                    if content:
                        assistant_message["content"] = (assistant_message.get("content") or "") + content
                        yield {"type": "delta", "text": content}
                    fr = choices[0].get("finish_reason")
                    if fr:
                        finish_reason = fr
    except Exception as exc:
        logger.warning("LLM 流式推理失败: %s", exc)
        return

    if tool_calls_by_index:
        assistant_message["tool_calls"] = []
        for idx in sorted(tool_calls_by_index):
            tc = tool_calls_by_index[idx]
            assistant_message["tool_calls"].append({
                "id": tc["id"],
                "type": tc["type"],
                "function": {
                    "name": tc["function"]["name"],
                    "arguments": tc["function"]["arguments"],
                },
            })
    yield {
        "type": "choice",
        "message": assistant_message,
        "finish_reason": finish_reason,
    }


async def summarize_text(text: str, style: str = "minutes") -> dict:
    settings = get_settings()
    api_key, base_url, model = resolve_credentials()
    clipped = text.strip()[: settings.deepseek_max_chars]
    if not clipped:
        raise bad_request("总结文本为空")

    instruction = STYLE_PROMPTS.get(style, STYLE_PROMPTS["minutes"])
    system = (
        "你是专业的中文会议与录音纪要助手。根据转写内容生成清晰、"
        f"准确的总结。{instruction}只输出总结正文，不要寒暄。"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"以下是需要总结的录音转写内容：\n\n{clipped}"},
        ],
        "temperature": 0.3,
    }
    url = f"{base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:500] if e.response is not None else str(e)
        raise bad_request(f"智能总结失败: {detail}") from e
    except httpx.HTTPError as e:
        raise bad_request(f"无法连接总结服务: {e}") from e

    choices = body.get("choices") or []
    if not choices:
        raise bad_request("总结服务返回空结果")
    summary = (choices[0].get("message", {}).get("content") or "").strip()
    if not summary:
        raise bad_request("总结内容为空")
    return {"summary": summary, "model": model}


async def summarize_article_content(*, title: str, text: str) -> dict:
    """为订阅收录的文章生成信息量充足的摘要。"""
    settings = get_settings()
    api_key, base_url, model = resolve_credentials()
    clipped = text.strip()[: settings.deepseek_max_chars]
    if not clipped:
        raise bad_request("正文过短，无法生成摘要")

    title_text = (title or "").strip() or "（无标题）"
    system = (
        "你是专业的中文内容编辑。请阅读用户提供的文章标题与正文，"
        "撰写一篇信息量充足的摘要。要求：\n"
        "1. 使用简体中文；\n"
        "2. 保留关键事实、数据、结论、时间、主体与因果，尽量不要遗漏重要信息；\n"
        "3. 避免空洞套话，不要编造正文中没有的内容；\n"
        "4. 可采用 2–4 个自然段或分点列表，篇幅约 150–450 字（正文很长时可适当加长）；\n"
        "5. 只输出摘要正文，不要输出标题、前缀标签或寒暄语。"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": f"标题：{title_text}\n\n正文：\n{clipped}",
            },
        ],
        "temperature": 0.25,
    }
    url = f"{base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0)) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:500] if e.response is not None else str(e)
        raise bad_request(f"文章摘要生成失败: {detail}") from e
    except httpx.HTTPError as e:
        raise bad_request(f"无法连接摘要服务: {e}") from e

    choices = body.get("choices") or []
    if not choices:
        raise bad_request("摘要服务返回空结果")
    summary = (choices[0].get("message", {}).get("content") or "").strip()
    if not summary:
        raise bad_request("摘要内容为空")
    return {"summary": summary, "model": model}


def _format_merged_blocks(merged_blocks: list[dict]) -> str:
    lines = []
    for i, block in enumerate(merged_blocks, 1):
        sp = block.get("speaker", "说话人 1")
        start = float(block.get("start", 0))
        end = float(block.get("end", start))
        m1, s1 = int(start // 60), int(start % 60)
        m2, s2 = int(end // 60), int(end % 60)
        tr = f"{m1}:{s1:02d}–{m2}:{s2:02d}"
        text = str(block.get("text") or "").strip()
        lines.append(f"[{i}] {sp} [{tr}]\n{text}")
    return "\n\n".join(lines)


async def summarize_speaker_timeline(
    merged_blocks: list[dict], style: str = "minutes"
) -> dict:
    """Summarize each merged speaker block; return JSON array string in summary field."""
    api_key, base_url, model = resolve_credentials()
    if not merged_blocks:
        raise bad_request("没有可总结的说话人片段")

    instruction = STYLE_PROMPTS.get(style, STYLE_PROMPTS["minutes"])
    blocks_text = _format_merged_blocks(merged_blocks)
    system = (
        "你是专业的中文会议与录音纪要助手。根据带说话人与时间戳的转写片段，"
        f"为每个片段生成简短摘要。{instruction}"
        "以 JSON 数组字符串输出，每项含 index（从 1 起）、speaker、summary 字段。"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": blocks_text},
        ],
        "temperature": 0.3,
    }
    url = f"{base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:500] if e.response is not None else str(e)
        raise bad_request(f"智能总结失败: {detail}") from e
    except httpx.HTTPError as e:
        raise bad_request(f"无法连接总结服务: {e}") from e

    choices = body.get("choices") or []
    if not choices:
        raise bad_request("总结服务返回空结果")
    summary = (choices[0].get("message", {}).get("content") or "").strip()
    if not summary:
        raise bad_request("总结内容为空")
    return {"summary": summary, "model": model}
