"""Playwright async API 与 asyncio 事件循环兼容（避免 sync API 跨线程卡死）。"""

import asyncio

from app.integrations.browser_automation.playwright_session import get_browser_session_manager


def test_browser_session_manager_is_singleton():
    assert get_browser_session_manager() is get_browser_session_manager()


def test_browser_navigate_completes_on_event_loop():
    async def _run():
        mgr = get_browser_session_manager()
        state = await mgr.get_session(
            user_id="pytest-nav",
            conversation_id="pytest-nav",
            headless=True,
        )
        try:
            result = await asyncio.wait_for(
                mgr.navigate(
                    state,
                    "https://www.tanshichang.cn",
                    allowed_domains="",
                ),
                timeout=45,
            )
            assert "tanshichang" in result["url"]
            assert result.get("title")
        finally:
            await mgr.close_session(user_id="pytest-nav", conversation_id="pytest-nav")

    asyncio.run(_run())
