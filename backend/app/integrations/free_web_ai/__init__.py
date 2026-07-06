"""Free Web AI Bridge — 通过 Playwright 操控免费网页 AI（豆包/千问/DeepSeek）。

用于在平台内集成免费网页 AI 能力，支持文本对话、图片生成、识图问答。

通过 Chrome persistent context 保存登录态，各 AI 网站只需手动登录一次。
"""

from __future__ import annotations

from app.integrations.free_web_ai.manager import FreeWebAiManager

__all__ = ["FreeWebAiManager"]

_manager: FreeWebAiManager | None = None


def get_free_web_ai_manager() -> FreeWebAiManager:
    global _manager
    if _manager is None:
        _manager = FreeWebAiManager()
    return _manager


async def shutdown_manager() -> None:
    global _manager
    if _manager is not None:
        await _manager.shutdown()
        _manager = None
