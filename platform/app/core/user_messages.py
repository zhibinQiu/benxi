"""返回给终端用户的文案（不含内部产品名）。"""

from __future__ import annotations

import re

KNOWLEDGE_SERVICE_UNAVAILABLE = "知识服务暂不可用，请稍后重试或联系管理员。"
KNOWLEDGE_WEB_UNAVAILABLE = "知识服务界面暂不可达，请稍后重试或联系管理员。"
KNOWLEDGE_NOT_ENABLED = "知识问答未启用，请联系管理员。"
KNOWLEDGE_SYNC_DISABLED = "知识库同步未启用，请联系管理员。"
KNOWLEDGE_NOT_READY = "知识服务未就绪，请稍后重试。"
KNOWLEDGE_SYNC_FAILED = "同步到知识库失败，请稍后重试或联系管理员。"
KNOWLEDGE_SYNC_NO_KB = "无法创建或访问目标知识库，请先打开「切片管理」完成知识库开户。"
KNOWLEDGE_SYNC_NO_FILE = "文档尚未上传文件，无法同步知识库。"
KNOWLEDGE_SYNC_UPLOAD_FAILED = "文档上传到知识库失败，请确认知识服务正常运行。"
KNOWLEDGE_SYNC_OK = "已同步到知识库。"

_VENDOR_RE = re.compile(r"ragflow|knowflow", re.I)


def sanitize_user_message(message: str | None, *, fallback: str = "") -> str:
    text = (message or "").strip()
    if not text:
        return fallback
    lower = text.lower()
    if "password" in lower and ("match" in lower or "不匹配" in text):
        return fallback or KNOWLEDGE_SERVICE_UNAVAILABLE
    if _VENDOR_RE.search(text) or "服务器内部" in text or "Internal Server" in text:
        return fallback or KNOWLEDGE_SERVICE_UNAVAILABLE
    return text
