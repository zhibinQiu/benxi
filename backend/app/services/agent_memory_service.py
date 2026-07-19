"""AI 智能体记忆层 — 跨会话 MEMORY.md，每轮注入 system，亦可通过工具按需读取。"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.core.text_utils import truncate_text
from app.storage.object_store import StorageObjectNotFoundError, get_object_store

_logger = logging.getLogger(__name__)
_TZ = ZoneInfo("Asia/Shanghai")
_TRUNC = "\n…（记忆已截断）"
# 同轮 specialist context + synth 可能各读一次；短 TTL 避免重复对象存储 IO
_MEMORY_PROMPT_TTL_SEC = 8.0
_memory_prompt_cache: dict[str, tuple[float, str]] = {}


def _memory_key(user_id: uuid.UUID) -> str:
    return f"agent-memory/{user_id}/MEMORY.md"


def read_user_memory(user_id: uuid.UUID, *, max_chars: int | None = None) -> str:
    """读取用户 MEMORY.md；不存在时返回空字符串。"""
    settings = get_settings()
    budget = max_chars if max_chars is not None else max(500, settings.agent_memory_read_max_chars)
    key = _memory_key(user_id)
    try:
        raw = get_object_store().get_object_bytes(key).decode("utf-8")
    except (FileNotFoundError, StorageObjectNotFoundError, UnicodeDecodeError):
        return ""
    except Exception:
        _logger.exception("read agent memory failed user=%s", user_id)
        return ""
    return truncate_text(raw.strip(), budget, suffix=_TRUNC)


MEMORY_TEMPLATE = (
    "# Agent Memory\n\n"
    "## 👤 角色设定\n\n"
    "你的身份背景、角色定位等。\n\n"
    "## 🎯 回复要求\n\n"
    "你对 AI 回复风格和内容的偏好。\n\n"
    "## ✅ 常用指令与工作流偏好\n\n"
    "你的开发习惯和常用流程。\n\n"
    "## 🔧 技术栈 & 约定\n\n"
    "项目的技术栈和约定。\n\n"
    "## 📝 其他需要记住的内容\n\n"
    "其他你想让 AI 长期记住的信息。\n"
)

_MEMORY_OVERRIDE_HINT = "以记忆为准：名称与偏好优先于默认自称「小析」。"


def _invalidate_memory_prompt_cache(user_id: uuid.UUID) -> None:
    _memory_prompt_cache.pop(str(user_id), None)


def build_memory_prompt_context(user_id: uuid.UUID) -> str:
    """将 MEMORY.md 格式化为每轮 system 注入块；无内容时返回空字符串。"""
    cache_key = str(user_id)
    now = time.monotonic()
    cached = _memory_prompt_cache.get(cache_key)
    if cached is not None and now - cached[0] < _MEMORY_PROMPT_TTL_SEC:
        return cached[1]
    body = read_user_memory(user_id)
    if not body.strip():
        result = ""
    else:
        result = f"【用户记忆】\n{body.strip()}\n\n{_MEMORY_OVERRIDE_HINT}"
    _memory_prompt_cache[cache_key] = (now, result)
    return result


def write_user_memory(user_id: uuid.UUID, content: str) -> bool:
    """覆盖写入 MEMORY.md（管理界面用）。"""
    settings = get_settings()
    max_total = max(1000, settings.agent_memory_max_chars)
    text = (content or "").strip()
    if not text:
        return clear_user_memory(user_id)
    if not text.startswith("#"):
        text = f"# Agent Memory\n\n{text}"
    body = truncate_text(text, max_total, suffix=_TRUNC)
    try:
        get_object_store().put_object_bytes(
            _memory_key(user_id),
            body.encode("utf-8"),
            "text/markdown; charset=utf-8",
        )
        _invalidate_memory_prompt_cache(user_id)
        return True
    except Exception:
        _logger.exception("write agent memory failed user=%s", user_id)
        return False


def clear_user_memory(user_id: uuid.UUID) -> bool:
    try:
        get_object_store().delete_object(_memory_key(user_id))
        _invalidate_memory_prompt_cache(user_id)
        return True
    except Exception:
        _logger.exception("clear agent memory failed user=%s", user_id)
        return False


def append_user_memory(user_id: uuid.UUID, note: str) -> bool:
    """追加一条带时间戳的记忆；超出总上限时保留最新内容。"""
    text = (note or "").strip()
    if not text:
        return False
    settings = get_settings()
    max_total = max(1000, settings.agent_memory_max_chars)
    max_entry = max(200, settings.agent_memory_entry_max_chars)
    entry = truncate_text(text, max_entry, suffix="…")
    stamp = datetime.now(timezone.utc).astimezone(_TZ).strftime("%Y-%m-%d %H:%M")
    line = f"- [{stamp}] {entry}"

    store = get_object_store()
    key = _memory_key(user_id)
    existing = ""
    try:
        existing = store.get_object_bytes(key).decode("utf-8").strip()
    except (FileNotFoundError, StorageObjectNotFoundError, UnicodeDecodeError):
        pass
    except Exception:
        _logger.exception("read before append memory failed user=%s", user_id)

    if existing:
        body = f"{existing}\n{line}"
    else:
        body = f"# Agent Memory\n\n{line}"

    body = truncate_text(body, max_total, suffix=_TRUNC)
    try:
        store.put_object_bytes(key, body.encode("utf-8"), "text/markdown; charset=utf-8")
        _invalidate_memory_prompt_cache(user_id)
        return True
    except Exception:
        _logger.exception("append agent memory failed user=%s", user_id)
        return False
