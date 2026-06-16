"""平台语言模型调用（OpenAI 兼容 chat/completions）— 用于纪要、摘要、问答等。"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import tomllib

from app.config import get_settings
from app.core.exceptions import bad_request

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
    from app.database import SessionLocal
    from app.services.model_settings_service import get_llm_credentials

    with SessionLocal() as db:
        return get_llm_credentials(db)


def resolve_credentials() -> tuple[str, str, str]:
    """返回 (api_key, base_url, model)；优先资源管理中的语言模型配置。"""
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
    base, key, model = _platform_llm_credentials()
    if _clean_key(key) and (base or "").strip() and (model or "").strip():
        return True
    fk, _, _ = _load_from_pdf2zh_config()
    return bool(fk)


def _chat_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/chat/completions"


def _clip_user_content(content: str, max_chars: int | None = None) -> str:
    limit = max_chars if max_chars is not None else get_settings().deepseek_max_chars
    return (content or "").strip()[:limit]


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
    payload_messages = []
    for msg in messages:
        role = str(msg.get("role") or "user")
        content = msg.get("content") or ""
        if role == "user" and max_user_chars is not None:
            content = _clip_user_content(str(content), max_user_chars)
        elif role == "user":
            content = _clip_user_content(str(content))
        payload_messages.append({"role": role, "content": content})
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                _chat_url(base_url),
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": payload_messages,
                    "temperature": temperature,
                },
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


async def chat_completion_stream(
    *,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
    timeout: float = 90.0,
    max_user_chars: int | None = None,
) -> AsyncIterator[str]:
    """流式 chat/completions；未配置或失败时不产出。"""
    if not is_configured():
        return
    try:
        api_key, base_url, model = resolve_credentials()
    except Exception:
        return
    payload_messages = []
    for msg in messages:
        role = str(msg.get("role") or "user")
        content = msg.get("content") or ""
        if role == "user" and max_user_chars is not None:
            content = _clip_user_content(str(content), max_user_chars)
        elif role == "user":
            content = _clip_user_content(str(content))
        payload_messages.append({"role": role, "content": content})
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                _chat_url(base_url),
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": payload_messages,
                    "temperature": temperature,
                    "stream": True,
                },
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
                    delta = (
                        chunk.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content")
                    )
                    if delta:
                        yield delta
    except Exception as exc:
        logger.warning("LLM 流式调用失败: %s", exc)


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
