"""FreeWebAiManager — Playwright 浏览器会话管理 + Provider 降级编排。"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from playwright.async_api import Browser, BrowserContext, Page

from app.integrations.free_web_ai.adapters import (
    PROVIDER_CHAIN,
    get_adapter,
)
from app.integrations.free_web_ai.config import FreeWebAiConfig, get_free_web_ai_config
from app.integrations.free_web_ai.engine import run_pipeline, stream_run_pipeline

logger = logging.getLogger(__name__)


class FreeWebAiManager:
    """免费网页 AI 管理器。

    通过 Playwright persistent context 桥接各 AI 网站。
    支持连续对话（上下文记忆）和平台选择。

    使用方式:
        manager = get_free_web_ai_manager()
        result = await manager.chat("用 Python 写排序")
        result = await manager.chat("加个注释")  # 自动沿用上下文
        result = await manager.chat("画只猫", provider="doubao")
    """

    def __init__(self, config: FreeWebAiConfig | None = None) -> None:
        self._config = config or get_free_web_ai_config()
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._pages: dict[str, Page] = {}
        self._lock = asyncio.Lock()
        self._initialized = False
        # 会话追踪：provider_key -> 是否已有活跃对话
        self._conversation_active: dict[str, bool] = {}

    async def _ensure_browser(self) -> None:
        """确保 Playwright browser + persistent context 已就绪。"""
        if self._initialized and self._browser:
            return
        async with self._lock:
            if self._initialized and self._browser:
                return
            await self._launch()

    async def _launch(self) -> None:
        """启动或连接浏览器。"""
        from playwright.async_api import async_playwright

        cfg = self._config

        # 方式1: 连接到已有 Chrome CDP（如用户已启动调试模式）
        if cfg.cdp_port > 0:
            try:
                pw = await async_playwright().start()
                cdp_url = f"http://127.0.0.1:{cfg.cdp_port}"
                self._browser = await pw.chromium.connect_over_cdp(cdp_url)
                # 已有浏览器，取现有 context
                contexts = self._browser.contexts
                if contexts:
                    self._context = contexts[0]
                else:
                    self._context = await self._browser.new_context(
                        viewport={"width": 1280, "height": 720},
                        locale="zh-CN",
                    )
                self._initialized = True
                ver = self._browser.version if hasattr(self._browser, "version") else "?"
                logger.info(
                    "已连接 Chrome CDP (port=%s), browser=%s",
                    cfg.cdp_port,
                    ver,
                )
                return
            except Exception as exc:
                logger.warning("CDP 连接失败, 回退启动独立浏览器: %s", exc)

        # 方式2: 启动独立浏览器（用 persistent context 保存登录态）
        import os as _os

        pw = await async_playwright().start()

        # 自动检测无头模式：当配置为非无头但 DISPLAY 不可用时强制回退
        headless = cfg.headless
        if not headless and not _os.environ.get("DISPLAY"):
            logger.warning(
                "DISPLAY 未设置，强制启用无头模式 (原配置 headless=%s)",
                headless,
            )
            headless = True

        launch_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        if cfg.proxy_server:
            launch_args.append(f"--proxy-server={cfg.proxy_server}")

        launch_kwargs = dict(
            user_data_dir=cfg.profile_dir,
            headless=headless,
            args=launch_args,
            viewport={"width": 1280, "height": 720},
            locale="zh-CN",
            timeout=60000,
        )
        if cfg.chrome_path:
            if _os.path.isfile(cfg.chrome_path):
                launch_kwargs["executable_path"] = cfg.chrome_path
            else:
                logger.warning(
                    "chrome_path 不存在, 使用 Playwright 内置 Chromium: %s",
                    cfg.chrome_path,
                )

        self._context = await pw.chromium.launch_persistent_context(**launch_kwargs)
        self._browser = self._context.browser
        self._initialized = True
        logger.info(
            "已启动独立浏览器 (headless=%s, profile=%s, chrome=%s)",
            cfg.headless, cfg.profile_dir, cfg.chrome_path or "default",
        )

    async def _get_page(self, adapter_key: str) -> Page:
        """获取或创建 provider 标签页。"""
        await self._ensure_browser()

        # 复用已有标签
        existing = self._pages.get(adapter_key)
        if existing:
            try:
                url = existing.url
                if url and "about:blank" not in url:
                    return existing
            except Exception:
                pass

        # 在已有页面中找匹配的标签
        for page in self._context.pages:
            try:
                url = page.url
                if url and adapter_key in url:
                    self._pages[adapter_key] = page
                    return page
            except Exception:
                continue

        # 新建标签
        page = await self._context.new_page()
        self._pages[adapter_key] = page
        return page

    async def _try_provider(
        self,
        adapter_key: str,
        prompt: str,
        *,
        image_path: str | None = None,
        image_gen: bool = False,
        timeout_ms: int | None = None,
        fresh_conversation: bool = True,
    ) -> dict[str, Any]:
        """尝试单个 provider。"""
        adapter = get_adapter(adapter_key)
        if not adapter:
            return {"success": False, "reason": f"未知 provider: {adapter_key}", "provider": adapter_key}

        page = await self._get_page(adapter_key)
        cfg = self._config
        timeout = timeout_ms or cfg.per_provider_timeout_ms

        result = await run_pipeline(
            page,
            adapter,
            prompt,
            float(timeout),
            image_path=image_path,
            image_gen=image_gen,
            fresh_conversation=fresh_conversation,
        )
        if result.get("success"):
            self._conversation_active[adapter_key] = True
        return result

    async def chat(
        self,
        prompt: str,
        *,
        provider: str | None = None,
        timeout_ms: int | None = None,
        new_conversation: bool = False,
    ) -> dict[str, Any]:
        """文本对话 — 自动 fallback 或指定 provider。

        new_conversation=True 强制新建对话（不沿用上下文）。
        默认为 False，自动沿用已有对话（上下文记忆）。

        Returns:
            {"success": True, "response": str, "provider": str}
            or {"success": False, "reason": str, "reasons": dict}
        """
        cfg = self._config
        timeout = timeout_ms or cfg.default_timeout_ms

        if provider:
            key = provider.lower()
            fresh = new_conversation or not self._conversation_active.get(key, False)
            return await self._try_provider(key, prompt, timeout_ms=timeout, fresh_conversation=fresh)

        # Fallback 链
        reasons: dict[str, str] = {}
        for adapter in PROVIDER_CHAIN:
            key = adapter["key"]
            fresh = new_conversation or not self._conversation_active.get(key, False)
            result = await self._try_provider(key, prompt, timeout_ms=timeout, fresh_conversation=fresh)
            if result.get("success"):
                return result
            reasons[key] = result.get("reason", "unknown")

        return {"success": False, "reason": "所有 provider 不可用", "reasons": reasons}

    async def reset_conversation(self, provider: str | None = None) -> None:
        """清除上下文，下次调用自动新建对话。"""
        if provider:
            self._conversation_active.pop(provider.lower(), None)
        else:
            self._conversation_active.clear()

    async def generate_image(
        self,
        prompt: str,
        *,
        provider: str | None = None,
        timeout_ms: int | None = None,
        new_conversation: bool = False,
    ) -> dict[str, Any]:
        """文字生图 — 优先豆包/千问。"""
        cfg = self._config
        timeout = timeout_ms or cfg.per_provider_timeout_ms
        providers = [provider] if provider else list(cfg.image_gen_providers)

        reasons: dict[str, str] = {}
        for key in providers:
            fresh = new_conversation or not self._conversation_active.get(key, False)
            result = await self._try_provider(
                key, prompt, image_gen=True, timeout_ms=timeout, fresh_conversation=fresh,
            )
            if result.get("success"):
                return result
            reasons[key] = result.get("reason", "unknown")

        return {"success": False, "reason": "所有生图 provider 不可用", "reasons": reasons}

    # ── 流式方法 ──

    async def _try_provider_stream(
        self,
        adapter_key: str,
        prompt: str,
        *,
        image_path: str | None = None,
        image_gen: bool = False,
        timeout_ms: int | None = None,
        fresh_conversation: bool = True,
    ) -> AsyncIterator[dict[str, Any]]:
        """流式版 _try_provider — 使用 stream_run_pipeline。"""
        adapter = get_adapter(adapter_key)
        if not adapter:
            yield {"type": "error", "reason": f"未知 provider: {adapter_key}"}
            return

        page = await self._get_page(adapter_key)
        cfg = self._config
        timeout = timeout_ms or cfg.per_provider_timeout_ms

        async for chunk in stream_run_pipeline(
            page,
            adapter,
            prompt,
            float(timeout),
            image_path=image_path,
            image_gen=image_gen,
            fresh_conversation=fresh_conversation,
        ):
            yield chunk

        # 所有 chunk 消费完毕后再标记会话活跃
        self._conversation_active[adapter_key] = True

    async def stream_chat(
        self,
        prompt: str,
        *,
        provider: str | None = None,
        timeout_ms: int | None = None,
        new_conversation: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        """流式文本对话 — 边生成边 yield 中间文本。"""
        cfg = self._config
        timeout = timeout_ms or cfg.default_timeout_ms

        if provider:
            key = provider.lower()
            fresh = new_conversation or not self._conversation_active.get(key, False)
            async for chunk in self._try_provider_stream(
                key, prompt, timeout_ms=timeout, fresh_conversation=fresh,
            ):
                yield chunk
            return

        # Fallback 链（流式只尝试第一个可用 provider）
        reasons: dict[str, str] = {}
        for adp in PROVIDER_CHAIN:
            key = adp["key"]
            fresh = new_conversation or not self._conversation_active.get(key, False)
            async for chunk in self._try_provider_stream(
                key, prompt, timeout_ms=timeout, fresh_conversation=fresh,
            ):
                if chunk.get("type") == "error":
                    reasons[key] = chunk.get("reason", "unknown")
                    break  # 试下一个
                yield chunk
                if chunk.get("type") == "done":
                    return
            else:
                # 没有 break（没遇到 error）→ 成功
                return

        yield {"type": "error", "reason": "所有 provider 不可用", "reasons": reasons}

    async def stream_generate_image(
        self,
        prompt: str,
        *,
        provider: str | None = None,
        timeout_ms: int | None = None,
        new_conversation: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        """流式生图 — 边生成边 yield 中间文本，完成后 yield 图片 URL。"""
        cfg = self._config
        timeout = timeout_ms or cfg.per_provider_timeout_ms
        providers = [provider] if provider else list(cfg.image_gen_providers)

        for key in providers:
            fresh = new_conversation or not self._conversation_active.get(key, False)
            async for chunk in self._try_provider_stream(
                key, prompt, image_gen=True, timeout_ms=timeout, fresh_conversation=fresh,
            ):
                if chunk.get("type") == "error":
                    continue  # 试下一个 provider
                yield chunk
                if chunk.get("type") in ("done", "error"):
                    return
        else:
            yield {"type": "error", "reason": "所有生图 provider 不可用"}

    async def ask_with_image(
        self,
        question: str,
        image_path: str,
        *,
        provider: str | None = None,
        timeout_ms: int | None = None,
        new_conversation: bool = False,
    ) -> dict[str, Any]:
        """识图问答 — 上传图片并提问。"""
        cfg = self._config
        timeout = timeout_ms or cfg.per_provider_timeout_ms
        providers = [provider] if provider else list(cfg.image_ask_providers)

        reasons: dict[str, str] = {}
        for key in providers:
            fresh = new_conversation or not self._conversation_active.get(key, False)
            result = await self._try_provider(
                key, question, image_path=image_path, timeout_ms=timeout,
                fresh_conversation=fresh,
            )
            if result.get("success"):
                return result
            reasons[key] = result.get("reason", "unknown")

        return {"success": False, "reason": "所有识图 provider 不可用", "reasons": reasons}

    async def smoke_test(self) -> list[dict[str, Any]]:
        """测试所有 provider 可达性。"""
        await self._ensure_browser()
        results: list[dict[str, Any]] = []
        for adapter in PROVIDER_CHAIN:
            key = adapter["key"]
            name = adapter["name"]
            url = adapter["url"]
            page = await self._get_page(key)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                current = page.url
                auth = any(d in current for d in adapter.get("auth_domains", []))
                results.append({
                    "provider": key,
                    "name": name,
                    "reachable": True,
                    "needs_login": auth,
                    "url": current[:80],
                })
            except Exception as exc:
                results.append({
                    "provider": key,
                    "name": name,
                    "reachable": False,
                    "error": str(exc),
                })
        return results

    async def shutdown(self) -> None:
        """关闭浏览器。CDP 模式下不清除用户浏览器。"""
        async with self._lock:
            if self._browser and self._config.cdp_port == 0:
                try:
                    await self._browser.close()
                except Exception as exc:
                    logger.debug("关闭浏览器时: %s", exc)
            self._browser = None
            self._context = None
            self._pages.clear()
            self._initialized = False
