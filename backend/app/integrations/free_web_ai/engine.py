"""10 步流水线引擎 — 操控网页 AI 的核心逻辑。

步骤:
  1. Navigate        → 导航到 AI 网页
  2. Auth check      → 检查登录状态
  3. Quota check     → 检测配额是否耗尽
  4. Overlay dismiss → 关闭弹窗/公告
  5. Pre-input hook  → 特殊前置操作（如新建会话）
  6. Upload image    → 图片上传（识图模式）
  7. Find editor     → 找到输入框
  8. Input + Send    → 输入提示词并发送
  9. Wait response   → 等待 AI 回复完成
  10. Extract        → 提取回复 + 后处理
"""

from __future__ import annotations

import asyncio
import re
import logging
from typing import AsyncIterator

from playwright.async_api import Locator, Page

logger = logging.getLogger(__name__)


def _normalize_text(s: str) -> str:
    """标准化文本比较：统一全角/半角标点、去除空格。"""
    return s.replace("：", ":").replace("；", ";").replace("，", ",").replace(" ", "").strip()


# ── 原子操作 ──


async def _find_editor(page: Page, selectors: list[str]) -> Locator | None:
    """在页面中按选择器顺序查找可编辑元素。"""
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                return el
        except Exception:
            logger.warning("_find_editor: query_selector failed for %s", sel, exc_info=True)
            continue
    return None


async def _input_text(page: Page, editor: Locator, text: str) -> None:
    """向编辑器输入文本 — fill / clipboard / 键盘兜底。"""
    try:
        await editor.evaluate("el => el.focus()")
        tag =         await editor.evaluate("el => el.tagName.toLowerCase()")
    except Exception:
        logger.warning("_input_text: evaluate focus/tag failed", exc_info=True)
        tag = "div"

    # 所有类型的编辑器都先尝试 fill（对 textarea, input, contenteditable 都有效）
    try:
        await editor.fill(text)
        return
    except Exception:
        logger.warning("_input_text: fill failed, will try clipboard", exc_info=True)
        pass

    # contenteditable → clipboard paste
    if tag != "textarea" and tag != "input":
        try:
            if len(text) <= 500:
                await page.evaluate(
                    "t => navigator.clipboard.writeText(t)", text
                )
                await editor.evaluate("() => document.execCommand('paste')")
                return
        except Exception:
            logger.warning("_input_text: clipboard paste failed, will type", exc_info=True)
            pass

    # 键盘逐段输入
    chunk_size = 150
    for i in range(0, len(text), chunk_size):
        chunk = text[i : i + chunk_size]
        await editor.type(chunk, delay=10)
        await asyncio.sleep(0.04)


async def _click_send(page: Page, editor: Locator, send_selectors: list[str]) -> bool:
    """点击发送按钮或使用 Enter 兜底。"""
    # 先尝试指定的选择器
    for sel in send_selectors:
        try:
            btn = await page.query_selector(sel)
            if btn:
                disabled = await btn.evaluate(
                    "el => el.disabled || el.getAttribute('aria-disabled') === 'true' || el.classList.contains('disabled')"
                )
                if not disabled:
                    await btn.click()
                    return True
        except Exception:
            logger.warning("_click_send: query_selector/click failed for %s", sel, exc_info=True)
            continue

    # Enter 键兜底
    try:
        await page.keyboard.press("Enter")
        return True
    except Exception:
        logger.warning("_click_send: Enter key fallback failed", exc_info=True)
        return False


async def _pre_input_deepseek_new_chat(page: Page) -> None:
    """DeepSeek 新建对话 — 通过侧栏新对话按钮或顶部。"""
    new_chat_selectors = [
        "div:has-text('开启新对话')",
        "a:has-text('开启新对话')",
        "button:has-text('新对话')",
        "[class*='new-chat'] button",
        "a[href*='new']",
    ]
    for sel in new_chat_selectors:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                await asyncio.sleep(2)
                return
        except Exception:
            logger.warning("_pre_input_deepseek_new_chat: failed for selector %s", sel, exc_info=True)
            continue


async def _pre_input_qwen_new_chat(page: Page) -> None:
    """千问新建对话 — 点击侧栏「新建对话」按钮。"""
    new_chat_selectors = [
        "button:has-text('新建对话')",
        "a:has-text('新建对话')",
        "div[class*='new'] button",
        "button[class*='new']",
    ]
    for sel in new_chat_selectors:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                await asyncio.sleep(2)
                return
        except Exception:
            logger.warning("_pre_input_qwen_new_chat: failed for selector %s", sel, exc_info=True)
            continue


async def _dismiss_overlays(page: Page, patterns: list[str]) -> None:
    """尝试关闭弹窗。"""
    close_selectors = [
        'button[aria-label*="关闭"]',
        'button[aria-label*="Close"]',
        'button[aria-label*="Dismiss"]',
        ".close-btn",
        ".dismiss-btn",
    ]
    for sel in close_selectors:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                await asyncio.sleep(0.5)
        except Exception:
            logger.warning("_dismiss_overlays: failed for selector %s", sel, exc_info=True)
            continue


async def _upload_image(page: Page, image_path: str) -> bool:
    """上传图片 — 通过文件选择器。"""
    upload_selectors = [
        'input[type="file"]',
        "button[aria-label*='图片']",
        "[class*='upload'] button",
    ]
    for sel in upload_selectors:
        try:
            el = await page.query_selector(sel)
            if not el:
                continue
            tag = await el.evaluate("el => el.tagName.toLowerCase()")
            if tag == "input":
                await el.set_input_files(image_path)
                await asyncio.sleep(3)
                return True
            else:
                await el.click()
                async with page.expect_file_chooser(timeout=10000) as fc_info:
                    pass
                file_chooser = await fc_info.value
                await file_chooser.set_files(image_path)
                await asyncio.sleep(3)
                return True
        except Exception:
            logger.warning("_upload_image: failed for selector %s", sel, exc_info=True)
            continue
    return False


async def _check_quota(page: Page, patterns: list[str]) -> bool:
    """检查页面文本是否包含限流模式。返回 True 表示配额耗尽。"""
    try:
        body = await page.evaluate("() => document.body.innerText || ''")
    except Exception:
        logger.warning("_check_quota: evaluate body text failed", exc_info=True)
        return False
    for pat in patterns:
        if re.search(pat, body, re.IGNORECASE):
            logger.warning("配额检测命中: %s", pat)
            return True
    return False


async def _get_body_text(page: Page) -> str:
    """获取页面 body 文本。"""
    try:
        return await page.evaluate("() => document.body.innerText || ''")
    except Exception:
        logger.warning("_get_body_text: evaluate failed", exc_info=True)
        return ""


# ── 已知 UI 噪声行（精确匹配，不是回答内容）──
_UI_NOISE_LINES = frozenset({
    "PPT 生成", "帮我写作", "图像生成", "视频生成",
    "解题答疑", "音乐生成", "下载电脑版",
})

# ── 搜索元数据模式（不作为回答提取）──
_SEARCH_META_PATTERNS = [
    re.compile(r"找到\s*\d+\s*篇资料"),
    re.compile(r"AI 生成.*可能有误"),
    re.compile(r"关键词[：:]"),
]


def _is_ui_noise_line(line: str) -> bool:
    """判断一行是否是已知 UI 噪声，不应作为回答内容。"""
    if not line or len(line) <= 2:
        return True
    if line in _UI_NOISE_LINES:
        return True
    for pat in _SEARCH_META_PATTERNS:
        if pat.search(line):
            return True
    return False


def _extract_content_lines(lines: list[str]) -> list[str]:
    """从行列表中过滤掉 UI 噪声，返回干净的内容行。"""
    return [l.strip() for l in lines if l.strip() and not _is_ui_noise_line(l.strip())]


async def _extract_body_content_after_prompt(page: Page) -> str | None:
    """在 body 中找到提示词之后的所有内容行（过滤 UI 噪声），返回多行文本。"""
    if not _last_prompt:
        return None
    try:
        body = await _get_body_text(page)
        idx = body.find(_last_prompt)
        if idx < 0:
            return None
        after = body[idx + len(_last_prompt):].strip()
        lines = [l.strip() for l in after.split("\n") if l.strip()]
        content = _extract_content_lines(lines)
        if content:
            return "\n".join(content)
    except Exception:
        logger.warning("_extract_body_content_after_prompt failed", exc_info=True)
        pass
    return None


async def _extract_body_diff(page: Page, prev_body: str) -> str | None:
    """对比 body diff，返回新的内容行。"""
    try:
        current = await _get_body_text(page)
        if not current or not prev_body:
            return None
        prev_lines = set(l.strip() for l in prev_body.split("\n") if l.strip())
        new_raw = [
            l.strip()
            for l in current.split("\n")
            if l.strip() and l.strip() not in prev_lines
        ]
        content = _extract_content_lines(new_raw)
        if content:
            return "\n".join(content)
    except Exception:
        logger.warning("_extract_body_diff failed", exc_info=True)
        pass
    return None


async def _extract_body_fallback(page: Page) -> str | None:
    """兜底：从 body 中提取所有内容行。"""
    try:
        body = await _get_body_text(page)
        lines = [l.strip() for l in body.split("\n") if l.strip()]
        content = _extract_content_lines(lines)
        if content:
            return "\n".join(content)
    except Exception:
        logger.warning("_extract_body_fallback failed", exc_info=True)
        pass
    return None


async def _extract_newest_response(
    page: Page, min_length: int = 5, prev_body: str = ""
) -> str | None:
    """从页面中提取最新的 AI 回复内容（支持多行）。

    策略：
    1. 先用适配器级别的 response_selectors 尝试提取（完整元素文本）
    2. 在 body 中找到提示词之后的所有内容（多行）
    3. diff 对比（新内容多行）
    4. 兜底
    """
    # 1. 适配器级选择器（最佳方式 —— 取准确元素内的完整文本）
    try:
        for sel in _current_response_selectors:
            els = await page.query_selector_all(sel)
            if els:
                text = await els[-1].evaluate("el => el.textContent || el.innerText || ''")
                text = (text or "").strip()
                if len(text) >= min_length:
                    return text
    except Exception:
        logger.warning("_extract_newest_response: response_selectors failed", exc_info=True)
        pass

    # 2. 提示词定位（取提示词之后过滤噪声的所有内容）
    result = await _extract_body_content_after_prompt(page)
    if result and len(result) >= min_length:
        return result

    # 3. Diff 对比
    result = await _extract_body_diff(page, prev_body)
    if result and len(result) >= min_length:
        return result

    # 4. 兜底
    result = await _extract_body_fallback(page)
    if result:
        return result
    return None


# 全局变量，用于 set_current_selectors 和 set_last_prompt 注入上下文
_current_response_selectors: list[str] = []
_current_extract_patterns: list[str] = []
_last_prompt: str = ""


def set_current_response_selectors(selectors: list[str]) -> None:
    """从 run_pipeline 注入当前适配器的 response_selectors。"""
    global _current_response_selectors
    _current_response_selectors = list(selectors)


def set_current_extract_patterns(patterns: list[str]) -> None:
    """注入提取模式，用于在 body 中定位 AI 回复。"""
    global _current_extract_patterns
    _current_extract_patterns = list(patterns)


def set_last_prompt(prompt: str) -> None:
    """记录当前 prompt，供 _extract_newest_response 定位 AI 回复。"""
    global _last_prompt
    _last_prompt = prompt


async def _wait_for_response(
    page: Page,
    cfg: dict[str, Any],
    timeout_ms: float,
    *,
    image_gen: bool = False,
) -> tuple[str, bool]:
    """等待 AI 回复，返回 (text, timed_out)。

    混合策略：停止按钮检测 + 文本稳定性检测。
    生图模式下还会检测页面中是否有大图出现，避免因文本无变化而过早返回。
    """
    stability_window = cfg.get("stability_window_ms", 10000) / 1000.0
    poll_interval = 2.0
    stop_selectors = cfg.get("stop_selectors", [])
    min_len = cfg.get("min_response_length", 5)
    stop_wait_mode = cfg.get("stop_wait_mode", "hidden")

    start = asyncio.get_event_loop().time()
    last_text = ""
    stable_start: float | None = None
    ever_seen_stop = False
    init_body = await _get_body_text(page)
    had_images = False

    while True:
        elapsed = asyncio.get_event_loop().time() - start
        remaining = (timeout_ms / 1000.0) - elapsed
        if remaining <= 0:
            text = await _extract_newest_response(page, min_length=1, prev_body=init_body)
            return (text or ""), True

        # 检查停止按钮
        stop_visible = False
        if stop_selectors:
            for sel in stop_selectors:
                try:
                    btn = await page.query_selector(sel)
                    if btn:
                        if stop_wait_mode == "detached":
                            stop_visible = True
                        else:
                            try:
                                stop_visible = await btn.is_visible()
                            except Exception:
                                logger.warning("_wait_for_response: stop_btn is_visible failed for %s", sel, exc_info=True)
                                stop_visible = False
                        if stop_visible:
                            break
                except Exception:
                    logger.warning("_wait_for_response: stop selector query failed for %s", sel, exc_info=True)
                    continue

        if ever_seen_stop and not stop_visible:
            text = await _extract_newest_response(page, min_length=min_len, prev_body=init_body)
            if text:
                return (text or ""), False
            # 停止按钮消失但提取内容为空 —— 可能是搜索阶段按钮，
            # 并非真正的生成完毕；重置信号继续等待。
            logger.debug("停止按钮消失但无可提取内容，续等真正回答")
            ever_seen_stop = False

        if stop_visible:
            ever_seen_stop = True

        # 生图模式：检测页面是否有大图出现（图片替代了文字回复）
        if image_gen:
            try:
                has_img = await page.evaluate("""
                    () => {
                        const imgs = document.querySelectorAll('img');
                        for (const img of imgs) {
                            const r = img.getBoundingClientRect();
                            if (r.width >= 80 && r.height >= 80) return true;
                        }
                        return false;
                    }
                """)
                if has_img and not had_images:
                    had_images = True
                    # 图片出现意味着 AI 开始回复，重置稳定性计时器
                    last_text = ""
                    stable_start = None
            except Exception:
                logger.warning("_wait_for_response: image gen detection failed", exc_info=True)
                pass

        # 文本稳定性检测
        current_body = await _get_body_text(page)
        body_changed = current_body and current_body != init_body
        if body_changed:
            if current_body == last_text:
                if stable_start is None:
                    stable_start = asyncio.get_event_loop().time()
                elif asyncio.get_event_loop().time() - stable_start >= stability_window:
                    text = await _extract_newest_response(page, min_length=min_len, prev_body=init_body)
                    if not text:
                        stable_start = None
                        continue
                    return (text or ""), False
            else:
                last_text = current_body
                stable_start = None
        else:
            # 没有停止按钮也未检测到变化，每 5s 尝试提取一次
            if not stop_selectors and elapsed > 10:
                text = await _extract_newest_response(page, min_length=min_len, prev_body=init_body)
                if text:
                    return (text or ""), False

        await asyncio.sleep(poll_interval)


async def _stream_wait_for_response(
    page: Page,
    cfg: dict[str, Any],
    timeout_ms: float,
) -> AsyncIterator[tuple[str, bool]]:
    """流式版 _wait_for_response：持续检测页面变化，逐次 yield 已累积的回复文本。

    Yields:
        (accumulated_text, is_done) — is_done=True 表示回复已完整或超时。
    """
    stability_window = cfg.get("stability_window_ms", 10000) / 1000.0
    poll_interval = 2.0
    stop_selectors = cfg.get("stop_selectors", [])
    min_len = cfg.get("min_response_length", 5)
    stop_wait_mode = cfg.get("stop_wait_mode", "hidden")

    start = asyncio.get_event_loop().time()
    init_body = await _get_body_text(page)
    last_yielded = ""
    prev_body = init_body
    stable_start: float | None = None
    ever_seen_stop = False

    while True:
        elapsed = asyncio.get_event_loop().time() - start
        remaining = (timeout_ms / 1000.0) - elapsed
        if remaining <= 0:
            text = (await _extract_newest_response(page, min_length=1, prev_body=init_body)) or ""
            yield (text, True)
            return

        # 检查停止按钮
        stop_visible = False
        if stop_selectors:
            for sel in stop_selectors:
                try:
                    btn = await page.query_selector(sel)
                    if btn:
                        if stop_wait_mode == "detached":
                            stop_visible = True
                        else:
                            try:
                                stop_visible = await btn.is_visible()
                            except Exception:
                                logger.warning("_stream_wait_for_response: stop_btn is_visible failed for %s", sel, exc_info=True)
                                stop_visible = False
                        if stop_visible:
                            break
                except Exception:
                    logger.warning("_stream_wait_for_response: stop selector query failed for %s", sel, exc_info=True)
                    continue

        if ever_seen_stop and not stop_visible:
            text = (await _extract_newest_response(page, min_length=min_len, prev_body=init_body)) or ""
            if text:
                if text != last_yielded:
                    yield (text, False)
                return
            # 搜索阶段按钮消失但无内容，续等真正回答
            logger.debug("(stream) 停止按钮消失但无可提取内容，续等")
            ever_seen_stop = False

        if stop_visible:
            ever_seen_stop = True

        # 检测 body 变化 — 有变化时尝试提取并 yield
        current_body = await _get_body_text(page)
        if current_body and current_body != init_body:
            if current_body == prev_body:
                if stable_start is None:
                    stable_start = asyncio.get_event_loop().time()
                elif asyncio.get_event_loop().time() - stable_start >= stability_window:
                    text = (await _extract_newest_response(page, min_length=min_len, prev_body=init_body)) or ""
                    if text != last_yielded:
                        yield (text, False)
                    return
            else:
                # 内容有更新，尝试提取
                extracted = await _extract_newest_response(page, min_length=1, prev_body=init_body)
                if extracted and extracted != last_yielded and len(extracted) > len(last_yielded):
                    yield (extracted, False)
                    last_yielded = extracted
                prev_body = current_body
                stable_start = None
        else:
            # 无停止按钮且无变化时，超时后尝试提取
            if not stop_selectors and elapsed > 10:
                text = (await _extract_newest_response(page, min_length=min_len, prev_body=init_body)) or ""
                if text and text != last_yielded:
                    yield (text, False)
                    return

        await asyncio.sleep(poll_interval)


async def _post_process(text: str, adapter_key: str) -> str:
    """后处理 — 模型名前缀裁剪等。"""
    if adapter_key == "qwen":
        text = re.sub(r"^Qwen[\d.]*-(?:Max|Plus|Turbo|Flash|72B)?[：:\s]*", "", text, flags=re.IGNORECASE)
    return text.strip()


async def _extract_image_urls(page: Page, adapter: dict) -> list[str]:
    """从页面中提取 AI 生成的图片 URL。

    优先用 response_selectors 缩小范围，找不到时改用尺寸过滤。
    blob: URL 会被转成 base64 data URL，避免浏览器隔离。
    """
    response_selectors = adapter.get("response_selectors", [])
    raw_srcs: list[str] = []

    # 1. 优先用 response selectors 找到回复容器内的 img
    for sel in response_selectors:
        try:
            imgs = await page.query_selector_all(f"{sel} img")
            for img in imgs:
                src = await img.get_attribute("src")
                if src and src.strip():
                    raw_srcs.append(src.strip())
        except Exception:
            logger.warning("_extract_image_urls: response_selectors img query failed for %s", sel, exc_info=True)
            continue
        if raw_srcs:
            break

    # 2. 兜底：扫描全页面 img，用尺寸排除小图标/头像
    if not raw_srcs:
        try:
            urls = await page.evaluate("""
                () => {
                    const imgs = document.querySelectorAll('img');
                    const results = [];
                    for (const img of imgs) {
                        const r = img.getBoundingClientRect();
                        if (r.width >= 80 && r.height >= 80) {
                            results.push(img.src);
                        }
                    }
                    return results;
                }
            """)
            raw_srcs.extend(urls or [])
        except Exception:
            logger.warning("_extract_image_urls: full page img scan failed", exc_info=True)
            pass

    # 3. blob: URL 转 base64 data URL；其它 URL 直接返回
    final: list[str] = []
    for src in raw_srcs:
        if src.startswith("blob:"):
            try:
                data_url = await page.evaluate(f"""
                    async () => {{
                        try {{
                            const resp = await fetch('{src}');
                            const blob = await resp.blob();
                            const ab = await blob.arrayBuffer();
                            const bytes = new Uint8Array(ab);
                            let binary = '';
                            const chunk = 8192;
                            for (let i = 0; i < bytes.length; i += chunk) {{
                                binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
                            }}
                            const b64 = btoa(binary);
                            return 'data:' + blob.type + ';base64,' + b64;
                        }} catch(e) {{
                            return null;
                        }}
                    }}
                """)
                if data_url:
                    final.append(data_url)
            except Exception:
                logger.warning("_extract_image_urls: blob to dataURL failed for %s", src[:50], exc_info=True)
                continue
        else:
            final.append(src)

    # 去重
    seen: set[str] = set()
    deduped: list[str] = []
    for u in final:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped


# ── 主流水线 ──


async def _page_healthy(page: Page, adapter: dict[str, Any]) -> bool:
    """检查页面是否还停留在正确的 provider 域名上。"""
    try:
        url = page.url
        # 检查 adapter 的 url 是否在当前页面地址中（可处理 key!=域名的情况）
        adapter_url = adapter.get("url", "")
        if adapter_url and adapter_url.rstrip("/") in url.rstrip("/"):
            return True
        # 同时也检查 key
        key = adapter.get("key", "")
        if key and key in url:
            return True
        for d in adapter.get("auth_domains", []):
            if d in url:
                return False
        return False
    except Exception:
        logger.warning("_page_healthy: url check failed", exc_info=True)
        return False


async def run_pipeline(
    page: Page,
    adapter: dict[str, Any],
    prompt: str,
    timeout_ms: float = 180000,
    *,
    image_path: str | None = None,
    image_gen: bool = False,
    image_gen_prefix: str | None = None,
    fresh_conversation: bool = True,
) -> dict[str, Any]:
    """执行 10 步流水线。

    Args:
        fresh_conversation: True=新建对话（导航+前处理）；
                           False=沿用当前对话（跳过导航和新建会话）。

    Returns:
        {"success": True, "response": str, "provider": str}
        or {"success": False, "reason": str}
    """
    key = adapter.get("key", "unknown")
    name = adapter.get("name", key)
    url = adapter.get("url", "")

    # 注入当前适配器的 response_selectors，供 _extract_newest_response 使用
    set_current_response_selectors(adapter.get("response_selectors", []))
    # 注入提取模式
    set_current_extract_patterns(adapter.get("extract_patterns", []))

    # ── Step 1: Navigate（优化——已在对的页面上则不跳转）──
    current_url = page.url
    already_on_page = url.rstrip("/") in current_url.rstrip("/")

    if fresh_conversation:
        if not already_on_page:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                nav_delay = adapter.get("nav_post_delay_ms", 0)
                if nav_delay:
                    await asyncio.sleep(nav_delay / 1000.0)
            except Exception as exc:
                return {"success": False, "reason": f"导航失败: {exc}", "provider": name}
        else:
            logger.debug("%s 页面已在目标 URL，跳过导航", name)

        # ── Step 2: Auth check ──
        try:
            current_url = page.url
        except Exception:
            logger.warning("run_pipeline: step2 auth check page.url failed", exc_info=True)
            current_url = ""
        auth_domains = adapter.get("auth_domains", [])
        if any(d in current_url for d in auth_domains):
            logger.warning("%s 需要登录", name)
            return {"success": False, "reason": "auth", "provider": name}
    else:
        if not await _page_healthy(page, adapter):
            if not already_on_page:
                logger.info("%s 页面不健康，回退为新建对话", name)
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    nav_delay = adapter.get("nav_post_delay_ms", 0)
                    if nav_delay:
                        await asyncio.sleep(nav_delay / 1000.0)
                except Exception as exc:
                    return {"success": False, "reason": f"导航失败: {exc}", "provider": name}
            else:
                logger.debug("%s 页面健康检查失败但 URL 匹配，跳过导航", name)
            fresh_conversation = True

    # ── Step 3: Quota check ──
    quota_patterns = adapter.get("quota_patterns", [])
    if quota_patterns:
        try:
            if await _check_quota(page, quota_patterns):
                return {"success": False, "reason": "quota", "provider": name}
        except Exception:
            logger.warning("run_pipeline: step3 quota check failed", exc_info=True)
            pass

    # ── Step 4: Overlay dismiss ──
    dismiss_patterns = adapter.get("dismiss_patterns", [])
    if dismiss_patterns:
        try:
            await _dismiss_overlays(page, dismiss_patterns)
        except Exception:
            logger.warning("run_pipeline: step4 overlay dismiss failed", exc_info=True)
            pass

    # ── Step 5: Pre-input hook（仅新建对话）──
    if fresh_conversation:
        pre_hook = adapter.get("pre_input_hook", "")
        if pre_hook == "deepseek_new_chat":
            await _pre_input_deepseek_new_chat(page)
        elif pre_hook == "qwen_new_chat":
            await _pre_input_qwen_new_chat(page)

    # ── Step 6: Upload image（识图模式）──
    if image_path and adapter.get("supports_image_upload", False):
        try:
            ok = await _upload_image(page, image_path)
            if not ok:
                logger.warning("%s 图片上传可能失败", name)
        except Exception as exc:
            logger.warning("%s 图片上传异常: %s", name, exc)

    # ── Step 7: Find editor ──
    editor_selectors = adapter.get("editor_selectors", [])
    editor = await _find_editor(page, editor_selectors)
    if not editor:
        return {"success": False, "reason": "找不到输入框", "provider": name}

    # ── Step 7.5: 生图模式 — 用生图前缀 ──
    if image_gen:
        prefix = image_gen_prefix or adapter.get("image_gen_prefix", "")
        prompt = f"{prefix}{prompt}"

    # 记录 prompt，供回复提取定位使用
    set_last_prompt(prompt)

    # ── Step 8: Input + Send ──
    try:
        await _input_text(page, editor, prompt)
    except Exception as exc:
        return {"success": False, "reason": f"输入失败: {exc}", "provider": name}

    try:
        sent = await _click_send(
            page,
            editor,
            adapter.get("send_selectors", []),
        )
        if not sent:
            return {"success": False, "reason": "发送失败", "provider": name}
    except Exception as exc:
        return {"success": False, "reason": f"发送异常: {exc}", "provider": name}

    # ── Step 9: Wait for response ──
    try:
        text, timed_out = await _wait_for_response(page, adapter, timeout_ms, image_gen=image_gen)
        if timed_out and not text:
            return {"success": False, "reason": "timeout", "provider": name}
        # 过滤掉与提示词相同的错误提取
        if text and _last_prompt and _normalize_text(text) == _normalize_text(_last_prompt):
            text = ""
    except Exception as exc:
        return {"success": False, "reason": f"等待回复异常: {exc}", "provider": name}

    # ── Step 9.5: 生图模式下提取页面中的图片 URL ──
    images: list[str] = []
    if image_gen:
        try:
            images = await _extract_image_urls(page, adapter)
            if images:
                logger.info("%s 提取到 %d 张生成图片", name, len(images))
        except Exception as exc:
            logger.warning("%s 提取图片异常: %s", name, exc)

    # ── Step 10: Post-process ──
    text = await _post_process(text, key)

    return {
        "success": True,
        "response": text,
        "provider": name,
        "timed_out": timed_out,
        "images": images,
    }


async def stream_run_pipeline(
    page: Page,
    adapter: dict[str, Any],
    prompt: str,
    timeout_ms: float = 180000,
    *,
    image_path: str | None = None,
    image_gen: bool = False,
    image_gen_prefix: str | None = None,
    fresh_conversation: bool = True,
) -> AsyncIterator[dict[str, Any]]:
    """流式 10 步流水线 — 同 run_pipeline 但边生成边 yield 增量文本。

    直接在"等待回复"阶段轮询页面变化，每发现新内容就 yield 一次，
    并在最后 yield 最终结果。

    Yields:
        {"type": "status", "message": str}  — 阶段提示（连接中、发送中等）
        {"type": "text", "content": str}     — 已累积的回复文本
        {"type": "images", "images": list}   — 生图模式下提取到的图片 URL
        {"type": "done", "response": str, "provider": str, "images": list}
        {"type": "error", "reason": str}
    """
    key = adapter.get("key", "unknown")
    name = adapter.get("name", key)
    url = adapter.get("url", "")

    # 注入上下文
    set_current_response_selectors(adapter.get("response_selectors", []))
    set_current_extract_patterns(adapter.get("extract_patterns", []))

    yield {"type": "status", "message": f"小析正在呼叫 {name} 同学…"}

    # ── Step 1: Navigate（优化——已在对的页面上则不跳转）──
    current_url = page.url
    already_on_page = url.rstrip("/") in current_url.rstrip("/")

    if fresh_conversation:
        if not already_on_page:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                nav_delay = adapter.get("nav_post_delay_ms", 0)
                if nav_delay:
                    await asyncio.sleep(nav_delay / 1000.0)
            except Exception as exc:
                yield {"type": "error", "reason": f"导航失败: {exc}", "provider": name}
                return
        else:
            logger.debug("%s 页面已在目标 URL，跳过导航", name)

        # ── Step 2: Auth check ──
        try:
            current_url = page.url
        except Exception:
            logger.warning("stream_run_pipeline: step2 auth check page.url failed", exc_info=True)
            current_url = ""
        auth_domains = adapter.get("auth_domains", [])
        if any(d in current_url for d in auth_domains):
            logger.warning("%s 需要登录", name)
            yield {"type": "error", "reason": "auth", "provider": name}
            return
    else:
        if not await _page_healthy(page, adapter):
            if not already_on_page:
                logger.info("%s 页面不健康，回退为新建对话", name)
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    nav_delay = adapter.get("nav_post_delay_ms", 0)
                    if nav_delay:
                        await asyncio.sleep(nav_delay / 1000.0)
                except Exception as exc:
                    yield {"type": "error", "reason": f"导航失败: {exc}", "provider": name}
                    return
            else:
                logger.debug("%s 页面健康检查失败但 URL 匹配，跳过导航", name)
            fresh_conversation = True

    # ── Step 3: Quota check ──
    quota_patterns = adapter.get("quota_patterns", [])
    if quota_patterns:
        try:
            if await _check_quota(page, quota_patterns):
                yield {"type": "error", "reason": "quota", "provider": name}
                return
        except Exception:
            logger.warning("stream_run_pipeline: step3 quota check failed", exc_info=True)
            pass

    # ── Step 4: Overlay dismiss ──
    dismiss_patterns = adapter.get("dismiss_patterns", [])
    if dismiss_patterns:
        try:
            await _dismiss_overlays(page, dismiss_patterns)
        except Exception:
            logger.warning("stream_run_pipeline: step4 overlay dismiss failed", exc_info=True)
            pass

    # ── Step 5: Pre-input hook（仅新建对话）──
    if fresh_conversation:
        pre_hook = adapter.get("pre_input_hook", "")
        if pre_hook == "deepseek_new_chat":
            await _pre_input_deepseek_new_chat(page)
        elif pre_hook == "qwen_new_chat":
            await _pre_input_qwen_new_chat(page)

    # ── Step 6: Upload image（识图模式）──
    if image_path and adapter.get("supports_image_upload", False):
        try:
            ok = await _upload_image(page, image_path)
            if not ok:
                logger.warning("%s 图片上传可能失败", name)
        except Exception as exc:
            logger.warning("%s 图片上传异常: %s", name, exc)

    # ── Step 7: Find editor ──
    editor_selectors = adapter.get("editor_selectors", [])
    editor = await _find_editor(page, editor_selectors)
    if not editor:
        yield {"type": "error", "reason": "找不到输入框", "provider": name}
        return

    # ── Step 7.5: 生图模式 — 用生图前缀 ──
    if image_gen:
        prefix = image_gen_prefix or adapter.get("image_gen_prefix", "")
        prompt = f"{prefix}{prompt}"

    set_last_prompt(prompt)

    yield {"type": "status", "message": f"{name} 正在生成…"}

    # ── Step 8: Input + Send ──
    try:
        await _input_text(page, editor, prompt)
    except Exception as exc:
        yield {"type": "error", "reason": f"输入失败: {exc}", "provider": name}
        return

    try:
        sent = await _click_send(page, editor, adapter.get("send_selectors", []))
        if not sent:
            yield {"type": "error", "reason": "发送失败", "provider": name}
            return
    except Exception as exc:
        yield {"type": "error", "reason": f"发送异常: {exc}", "provider": name}
        return

    # ── Step 9: 等待回复 ──
    # 生图模式：AI 以图片为主要输出，文本可能很少。
    # 直接等待固定时间让 AI 完成生成，然后提取图片。
    response_text = ""
    if image_gen:
        try:
            min_wait = min(25.0, timeout_ms / 1000.0)  # 最多等 25 秒
            start_ts = asyncio.get_event_loop().time()
            # 先等几秒让 AI 开始生成（缩短到 4 秒，多数平台 2-3s 即开始输出）
            await asyncio.sleep(4)
            # 然后轮询等待图片出现（最多到 min_wait 秒）
            while asyncio.get_event_loop().time() - start_ts < min_wait:
                has_img = False
                try:
                    has_img = await page.evaluate("""
                        () => {
                            const imgs = document.querySelectorAll('img');
                            for (const img of imgs) {
                                const r = img.getBoundingClientRect();
                                if (r.width >= 80 && r.height >= 80) return true;
                            }
                            return false;
                        }
                    """)
                except Exception:
                    logger.warning("stream_run_pipeline: image_gen has_img evaluate failed", exc_info=True)
                    pass
                if has_img:
                    break
                # 同时尝试提取文本，但跳过提示词
                raw = await _extract_newest_response(page, min_length=5)
                if raw and _last_prompt and not _normalize_text(_last_prompt) in _normalize_text(raw):
                    response_text = raw
                    yield {"type": "text", "content": response_text}
                await asyncio.sleep(2)
            # 最终再提取一次文本
            final_text = await _extract_newest_response(page, min_length=1)
            if final_text and _last_prompt and not _normalize_text(_last_prompt) in _normalize_text(final_text):
                if final_text != response_text:
                    response_text = final_text
                    yield {"type": "text", "content": response_text}
        except Exception as exc:
            yield {"type": "error", "reason": f"等待回复异常: {exc}", "provider": name}
            return
    else:
        # 文本对话 → 流式轮询，逐段 yield
        try:
            async for accumulated, is_done in _stream_wait_for_response(page, adapter, timeout_ms):
                if accumulated and accumulated != response_text:
                    # 跳过内容与提示词相同的错误提取（页面可能用全角标点）
                    if _last_prompt and (
                        _normalize_text(_last_prompt) in _normalize_text(accumulated)
                        or _normalize_text(accumulated) in _normalize_text(_last_prompt)
                    ):
                        continue
                    response_text = accumulated
                    yield {"type": "text", "content": accumulated}
                if is_done:
                    break
        except Exception as exc:
            yield {"type": "error", "reason": f"等待回复异常: {exc}", "provider": name}
            return

    # ── Step 9.5: 生图模式提取图片 ──
    images: list[str] = []
    if image_gen:
        try:
            images = await _extract_image_urls(page, adapter)
            if images:
                logger.info("%s 提取到 %d 张生成图片", name, len(images))
                yield {"type": "images", "images": images}
        except Exception as exc:
            logger.warning("%s 提取图片异常: %s", name, exc)

    # ── Step 10: Post-process ──
    text = await _post_process(response_text, key)

    if text or images:
        yield {"type": "done", "response": text, "provider": name, "images": images}
    else:
        yield {"type": "error", "reason": "回复为空", "provider": name}
