"""返回给终端用户的文案（不含内部产品名）。

设计原则：
- 对外 API / 后台任务 / 流式 SSE 均经 ``sanitize_user_message`` 或衍生函数过滤厂商名、
  堆栈片段、MinIO 键路径等，避免把 RAGFlow/PageIndex 内部错误直接展示给用户。
- 新增错误类型时优先在此增加常量与映射规则，勿在 view/service 内联字符串替换。
"""

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
KNOWLEDGE_QA_DOC_UNAVAILABLE = "《{title}》暂不可检索，请确认已上传文件并完成索引。"
DOCUMENT_COMPARE_NO_FILE = "《{title}》尚未上传文件，无法参与比对。"
STORAGE_FILE_MISSING = (
    "文档原始文件在对象存储中不存在，可能已被清理或未上传成功。"
    "请重新上传文件后再试；若仅需更换解析方式且知识库中仍有副本，可取消「全量同步」后重试。"
)
KNOWLEDGE_SYNC_UPLOAD_FAILED = "文档上传到知识库失败，请确认知识服务正常运行。"
KNOWLEDGE_SYNC_OK = "已同步到知识库。"

_VENDOR_RE = re.compile(r"ragflow|knowflow|pageindex", re.I)
_TECH_SETUP_RE = re.compile(
    r"pip install|third_party|pageindex-upstream|embedding|IMAGE2TEXT|"
    r"LiteLLM|向量|树搜索|树形索引",
    re.I,
)


def sanitize_user_message(message: str | None, *, fallback: str = "") -> str:
    """通用清洗：空值、密码提示、对象存储缺失、厂商/技术栈关键词 → fallback 或专用文案。"""
    text = (message or "").strip()
    if not text:
        return fallback
    lower = text.lower()
    if "password" in lower and ("match" in lower or "不匹配" in text):
        return fallback or KNOWLEDGE_SERVICE_UNAVAILABLE
    if (
        "nosuchkey" in lower
        or "getobject" in lower
        or "specified key does not exist" in lower
        or text.startswith("docs/")
    ):
        return STORAGE_FILE_MISSING
    if (
        _VENDOR_RE.search(text)
        or _TECH_SETUP_RE.search(text)
        or "服务器内部" in text
        or "Internal Server" in text
    ):
        return fallback or KNOWLEDGE_SERVICE_UNAVAILABLE
    return text


def http_exception_message(exc: BaseException, *, fallback: str = "") -> str:
    """FastAPI HTTPException → 用户可见文案。

    实现思路：从 ``detail`` 字典取 ``message`` 字段（与 ``AppError`` 格式一致），
    再交给 ``sanitize_user_message``。流式问答等无法直接 raise 的场景复用此函数。
    """
    from fastapi import HTTPException

    if not isinstance(exc, HTTPException):
        return sanitize_user_message(str(exc), fallback=fallback)
    detail = exc.detail
    raw = (
        str(detail.get("message") or detail)
        if isinstance(detail, dict)
        else str(detail)
    )
    return sanitize_user_message(raw, fallback=fallback)


def background_job_error_message(exc: BaseException, *, fallback: str = "操作失败") -> str:
    """后台任务异常 → 用户可见文案（KnowFlow / 存储 / HTTP / 通用）。

    实现思路：按异常类型分支——``KnowflowSyncError`` 取业务 message；
    ``StorageObjectNotFoundError`` 固定为 ``STORAGE_FILE_MISSING``；
    ``HTTPException`` 走 ``http_exception_message``；其余字符串清洗。
    写入 ``Job.error_message`` 与通知正文时统一调用，避免各 job runner 重复 if/else。
    """
    from fastapi import HTTPException

    from app.services.ragflow_sync_service import KnowflowSyncError
    from app.storage.object_store import StorageObjectNotFoundError

    if isinstance(exc, KnowflowSyncError):
        return sanitize_user_message(exc.message, fallback=fallback)
    if isinstance(exc, StorageObjectNotFoundError):
        return STORAGE_FILE_MISSING
    if isinstance(exc, HTTPException):
        return http_exception_message(exc, fallback=fallback)
    return sanitize_user_message(str(exc), fallback=fallback)
