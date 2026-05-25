from __future__ import annotations

import json
import re

import httpx

from app.core.exceptions import bad_request
from app.integrations.deepseek_client import is_configured, resolve_credentials
from app.schemas.todo import TodoLlmItem


def _strip_json_block(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


async def _chat(system: str, user: str) -> str:
    if not is_configured():
        raise bad_request("未配置 DeepSeek API，无法使用智能录入")
    api_key, base_url, model = resolve_credentials()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
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
        raise bad_request(f"智能处理失败: {detail}") from e
    except httpx.HTTPError as e:
        raise bad_request(f"无法连接 AI 服务: {e}") from e

    choices = body.get("choices") or []
    if not choices:
        raise bad_request("AI 返回为空")
    content = (choices[0].get("message", {}) or {}).get("content") or ""
    if not content.strip():
        raise bad_request("AI 返回为空")
    return content.strip()


def _normalize_items(data: object) -> list[TodoLlmItem]:
    if isinstance(data, dict) and "items" in data:
        data = data["items"]
    if not isinstance(data, list):
        raise bad_request("AI 返回格式无效")
    out: list[TodoLlmItem] = []
    for row in data:
        if isinstance(row, str):
            title = row.strip()
            if title:
                out.append(TodoLlmItem(title=title[:512]))
            continue
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        note = str(row.get("note") or "").strip()
        out.append(TodoLlmItem(title=title[:512], note=note[:2000]))
    if not out:
        raise bad_request("未能从文本中解析出待办项")
    return out


async def llm_parse_todos(text: str) -> list[TodoLlmItem]:
    system = (
        "你是待办事项助手。从用户输入中提取待办任务，输出严格 JSON："
        '{"items":[{"title":"任务标题","note":"可选备注"}]}。'
        "每条 title 简洁明确；无待办时返回 {\"items\":[]}。"
        "不要 markdown，不要解释。"
    )
    raw = await _chat(system, text.strip())
    try:
        data = json.loads(_strip_json_block(raw))
    except json.JSONDecodeError as e:
        raise bad_request("AI 返回的 JSON 无法解析") from e
    return _normalize_items(data)


async def llm_adjust_todos(text: str, pending: list[dict]) -> list[TodoLlmItem]:
    current = json.dumps(
        [{"title": p["title"], "note": p.get("note") or ""} for p in pending],
        ensure_ascii=False,
    )
    system = (
        "你是待办事项助手。根据用户指令调整「当前待办列表」。"
        "输出严格 JSON：{\"items\":[{\"title\":\"...\",\"note\":\"\"}]}，"
        "items 为调整后的完整待办列表（顺序即优先级，靠前更重要）。"
        "可合并、拆分、重排、增删；不要 markdown，不要解释。"
    )
    user = f"当前待办：\n{current}\n\n用户指令：\n{text.strip()}"
    raw = await _chat(system, user)
    try:
        data = json.loads(_strip_json_block(raw))
    except json.JSONDecodeError as e:
        raise bad_request("AI 返回的 JSON 无法解析") from e
    return _normalize_items(data)
