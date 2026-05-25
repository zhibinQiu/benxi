"""辅助写作 — DeepSeek 改写 Markdown。"""

from __future__ import annotations

import httpx

from app.core.exceptions import bad_request
from app.integrations.deepseek_client import is_configured, resolve_credentials

PRESET_PROMPTS: dict[str, dict[str, str]] = {
    "polish": {
        "label": "润色优化",
        "description": "保持原意，优化表达与结构",
        "system": (
            "你是专业的中文 Markdown 写作助手。根据用户原文与指令润色内容，"
            "输出完整 Markdown，不要解释，不要代码围栏。"
        ),
    },
    "expand": {
        "label": "扩写充实",
        "description": "在原有基础上补充细节与论据",
        "system": (
            "你是 Markdown 写作助手。在保持主题不变的前提下扩写，"
            "输出完整 Markdown，不要解释，不要代码围栏。"
        ),
    },
    "shorten": {
        "label": "精简压缩",
        "description": "删繁就简，保留核心信息",
        "system": (
            "你是 Markdown 写作助手。精简用户文稿，输出完整 Markdown，"
            "不要解释，不要代码围栏。"
        ),
    },
    "outline": {
        "label": "生成大纲",
        "description": "根据主题生成层级大纲",
        "system": (
            "你是 Markdown 写作助手。根据用户输入生成清晰的多级标题大纲，"
            "仅输出 Markdown 标题与要点列表，不要解释。"
        ),
    },
    "continue": {
        "label": "续写下文",
        "description": "在文末自然续写一段",
        "system": (
            "你是 Markdown 写作助手。根据已有正文续写后续内容，"
            "输出完整 Markdown（含原文与续写），不要解释，不要代码围栏。"
        ),
    },
    "formal": {
        "label": "公文正式",
        "description": "改为正式、规范的公文语体",
        "system": (
            "你是机关公文写作助手。将内容改为正式公文语体，"
            "输出完整 Markdown，不要解释，不要代码围栏。"
        ),
    },
    "carbon_report": {
        "label": "双碳报告",
        "description": "双碳/ESG 报告表述优化",
        "system": (
            "你是双碳与 ESG 领域写作助手。优化专业术语与数据表述，"
            "输出完整 Markdown，不要解释，不要代码围栏。"
        ),
    },
}


def list_presets() -> list[dict]:
    return [
        {
            "id": key,
            "label": meta["label"],
            "description": meta["description"],
        }
        for key, meta in PRESET_PROMPTS.items()
    ]


async def assist_markdown(
    *,
    markdown: str,
    instruction: str,
    preset_id: str | None = None,
) -> dict:
    if not is_configured():
        raise bad_request("未配置 DeepSeek API，无法使用 AI 辅助写作")

    preset = PRESET_PROMPTS.get(preset_id or "") if preset_id else None
    extra = (instruction or "").strip()
    if not preset and not extra:
        raise bad_request("请选择提示词模板或输入补充说明")

    system = preset["system"] if preset else (
        "你是 Markdown 写作助手。按用户指令处理文稿，"
        "只输出完整 Markdown，不要解释，不要代码围栏。"
    )
    user_parts = []
    if extra:
        user_parts.append(f"【用户指令】\n{extra}")
    if preset:
        user_parts.append(f"【任务类型】{preset['label']}")
    user_parts.append(f"【当前 Markdown 文稿】\n{markdown.strip() or '（空）'}")

    api_key, base_url, model = resolve_credentials()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(user_parts)},
        ],
        "temperature": 0.35,
    }
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0)) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:500] if e.response is not None else str(e)
        raise bad_request(f"AI 写作失败: {detail}") from e
    except httpx.HTTPError as e:
        raise bad_request(f"无法连接 AI 服务: {e}") from e

    choices = body.get("choices") or []
    if not choices:
        raise bad_request("AI 返回为空")
    content = (choices[0].get("message", {}) or {}).get("content") or ""
    content = _strip_fences(content.strip())
    if not content:
        raise bad_request("AI 未返回有效内容")
    return {"markdown": content, "model": model, "preset_id": preset_id}


def _strip_fences(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
