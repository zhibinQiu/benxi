"""Playwright 浏览器会话：Snapshot → Act 循环（async API，与 uvicorn 事件循环兼容）。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.integrations.browser_automation.browser_config import docker_launch_args
from app.integrations.browser_automation.url_guard import validate_browser_url

_logger = logging.getLogger(__name__)

_playwright_lock = asyncio.Lock()
_playwright_instance = None
_browser_instance = None
_launch_headless = True


async def _ensure_playwright(*, headless: bool = True):
    global _playwright_instance, _browser_instance, _launch_headless
    async with _playwright_lock:
        if _browser_instance is not None and _launch_headless == headless:
            return _browser_instance
        if _browser_instance is not None:
            try:
                await _browser_instance.close()
            except Exception:
                pass
            _browser_instance = None
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright 未安装，无法打开网页。"
                "本机开发: ./dev.sh browser setup ；"
                "Docker: ./dev.sh browser setup --docker ；"
                "服务器: INSTALL_BROWSER=1 docker compose build api worker && docker compose up -d api worker"
            ) from exc
        if _playwright_instance is None:
            _playwright_instance = await async_playwright().start()
        _launch_headless = headless
        _browser_instance = await _playwright_instance.chromium.launch(
            headless=headless,
            args=docker_launch_args(),
            timeout=60_000,
        )
        return _browser_instance


@dataclass
class BrowserSessionState:
    session_id: str
    user_id: str
    conversation_id: str
    page: Any = None
    context: Any = None
    last_url: str = ""
    step_count: int = 0
    workflow_steps: list[dict[str, Any]] = field(default_factory=list)
    ref_map: dict[str, Any] = field(default_factory=dict)


class BrowserSessionManager:
    """进程内 Playwright 会话管理（Phase 2 可换 Redis 跨 worker）。"""

    def __init__(self) -> None:
        self._sessions: dict[str, BrowserSessionState] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def session_key(user_id: str, conversation_id: str) -> str:
        conv = (conversation_id or "default").strip()
        return f"{user_id}:{conv}"

    async def get_session(
        self,
        *,
        user_id: str,
        conversation_id: str | None,
        create: bool = True,
        headless: bool = True,
    ) -> BrowserSessionState | None:
        key = self.session_key(user_id, conversation_id or "")
        async with self._lock:
            state = self._sessions.get(key)
            if state or not create:
                return state
            browser = await _ensure_playwright(headless=headless)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                locale="zh-CN",
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()
            state = BrowserSessionState(
                session_id=uuid.uuid4().hex[:12],
                user_id=user_id,
                conversation_id=conversation_id or "",
                page=page,
                context=context,
            )
            self._sessions[key] = state
            return state

    async def close_session(self, *, user_id: str, conversation_id: str | None) -> None:
        key = self.session_key(user_id, conversation_id or "")
        async with self._lock:
            state = self._sessions.pop(key, None)
        if not state:
            return
        try:
            if state.context:
                await state.context.close()
        except Exception as exc:
            _logger.debug("关闭浏览器 context 失败: %s", exc)

    def _record_step(self, state: BrowserSessionState, step: dict[str, Any]) -> None:
        state.step_count += 1
        state.workflow_steps.append(step)

    async def navigate(
        self,
        state: BrowserSessionState,
        url: str,
        *,
        allowed_domains: str = "",
    ) -> dict[str, Any]:
        safe_url = validate_browser_url(url, allowed_domains=allowed_domains)
        page = state.page
        try:
            await page.goto(safe_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            current = (page.url or "").strip()
            if not current or current in {"about:blank", ":"}:
                raise
            err_text = str(exc)
            if "ERR_ABORTED" not in err_text and "Timeout" not in type(exc).__name__:
                raise
            _logger.warning(
                "browser navigate continued after error: %s -> %s (%s)",
                safe_url,
                current,
                exc,
            )
        state.last_url = page.url
        step = {"action": "navigate", "url": safe_url}
        self._record_step(state, step)
        return {"url": state.page.url, "title": await state.page.title()}

    async def snapshot(self, state: BrowserSessionState) -> dict[str, Any]:
        page = state.page
        refs: list[dict[str, Any]] = []
        ref_map: dict[str, Any] = {}
        idx = 0

        for el in await page.locator(
            "a, button, input, select, textarea, [role='button'], [role='link'], "
            "[role='textbox'], [role='combobox'], [role='checkbox'], [role='radio']"
        ).all():
            try:
                if not await el.is_visible():
                    continue
            except Exception:
                continue
            idx += 1
            ref = f"e{idx}"
            role = await el.evaluate(
                "el => el.getAttribute('role') || el.tagName.toLowerCase()"
            )
            name = (
                await el.get_attribute("aria-label")
                or await el.get_attribute("placeholder")
                or await el.get_attribute("name")
                or (await el.inner_text() or "")[:80]
                or await el.get_attribute("id")
                or ""
            )
            value = ""
            if str(role or "").lower() in {"input", "textarea", "textbox"}:
                try:
                    value = await el.input_value()
                except Exception:
                    value = ""
            entry = {
                "ref": ref,
                "role": str(role or "").lower(),
                "name": (name or "").strip()[:120],
            }
            if value:
                entry["value"] = value[:200]
            refs.append(entry)
            ref_map[ref] = el

        state.ref_map = ref_map
        text_preview = ""
        try:
            text_preview = (await page.inner_text("body") or "")[:800]
        except Exception:
            pass

        return {
            "url": page.url,
            "title": await page.title(),
            "refs": refs[:80],
            "text_preview": text_preview,
        }

    def _resolve_ref(self, state: BrowserSessionState, ref: str):
        el = state.ref_map.get(ref)
        if el is None:
            raise ValueError(f"ref `{ref}` 已失效，请先 browser_snapshot 获取最新 ref")
        return el

    async def click(self, state: BrowserSessionState, ref: str) -> dict[str, Any]:
        el = self._resolve_ref(state, ref)
        hint = {}
        try:
            hint = {
                "ref": ref,
                "role": str(
                    await el.evaluate(
                        "el => el.getAttribute('role') || el.tagName.toLowerCase()"
                    )
                    or ""
                ).lower(),
                "name": (
                    await el.get_attribute("aria-label")
                    or await el.get_attribute("placeholder")
                    or await el.get_attribute("name")
                    or (await el.inner_text() or "")[:80]
                    or ""
                ).strip()[:120],
            }
        except Exception:
            hint = {"ref": ref}
        await el.click(timeout=10000)
        state.last_url = state.page.url
        step = {"action": "click", **hint}
        self._record_step(state, step)
        return {"url": state.page.url, "title": await state.page.title()}

    async def type_text(
        self,
        state: BrowserSessionState,
        ref: str,
        text: str,
        *,
        submit: bool = False,
    ) -> dict[str, Any]:
        el = self._resolve_ref(state, ref)
        hint = {"ref": ref}
        try:
            hint["role"] = str(
                await el.evaluate(
                    "el => el.getAttribute('role') || el.tagName.toLowerCase()"
                )
                or ""
            ).lower()
            hint["name"] = (
                await el.get_attribute("aria-label")
                or await el.get_attribute("placeholder")
                or await el.get_attribute("name")
                or ""
            ).strip()[:120]
        except Exception:
            pass
        await el.fill(text or "")
        if submit:
            await el.press("Enter")
        step = {"action": "type", "text": text, "submit": submit, **hint}
        self._record_step(state, step)
        return {"url": state.page.url, "title": await state.page.title()}

    async def fill_fields(
        self,
        state: BrowserSessionState,
        fields: list[dict[str, Any]],
    ) -> dict[str, Any]:
        for item in fields:
            ref = str(item.get("ref") or "").strip()
            value = str(item.get("value") or "")
            if not ref:
                continue
            el = self._resolve_ref(state, ref)
            await el.fill(value)
            self._record_step(
                state,
                {"action": "fill", "ref": ref, "value": value},
            )
        return {"url": state.page.url, "title": await state.page.title(), "filled": len(fields)}

    async def screenshot_png(
        self,
        state: BrowserSessionState,
        *,
        full_page: bool = False,
        max_kb: int = 800,
    ) -> tuple[bytes, str, str]:
        page = state.page
        try:
            raw = await page.screenshot(full_page=full_page, type="png", timeout=30000)
        except Exception as exc:
            err = str(exc)
            if "Target crashed" in err or "has been closed" in err:
                raise RuntimeError(
                    "页面渲染进程已崩溃（常见于百度等站点拦截无头浏览器）。"
                    "可尝试改用 Bing 搜索截图，或在管理后台关闭 headless 模式后重试。"
                ) from exc
            raise
        limit = max(64, int(max_kb)) * 1024
        if len(raw) > limit and full_page:
            raw = await page.screenshot(full_page=False, type="png", timeout=30000)
        self._record_step(state, {"action": "screenshot", "full_page": full_page})
        if len(raw) > limit:
            raw = raw[:limit]
        return raw, page.url, await page.title()


# 全局单例
_manager: BrowserSessionManager | None = None


def get_browser_session_manager() -> BrowserSessionManager:
    global _manager
    if _manager is None:
        _manager = BrowserSessionManager()
    return _manager
