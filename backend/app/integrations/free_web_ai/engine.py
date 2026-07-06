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
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


def _normalize_text(s: str) -> str:
    """标准化文本比较：统一全角/半角标点、去除空格。"""
    return s.replace("：", ":").replace("；", ";").replace("，", ",").replace(" ", "").strip()


# ── 原子操作 ──


async def _find_editor(page: Any, selectors: list[str]) -> Any | None:
    """在页面中按选择器顺序查找可编辑元素。"""
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                return el
        except Exception:
            continue
    return None


async def _input_text(page: Any, editor: Any, text: str) -> None:
    """向编辑器输入文本 — fill / clipboard / 键盘兜底。"""
    try:
        await editor.evaluate("el => el.focus()")
        tag = await editor.evaluate("el => el.tagName.toLowerCase()")
    except Exception:
        tag = "div"

    # 所有类型的编辑器都先尝试 fill（对 textarea, input, contenteditable 都有效）
    try:
        await editor.fill(text)
        return
    except Exception:
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
            pass

    # 键盘逐段输入
    chunk_size = 150
    for i in range(0, len(text), chunk_size):
        chunk = text[i : i + chunk_size]
        await editor.type(chunk, delay=10)
        await asyncio.sleep(0.04)


async def _click_send(page: Any, editor: Any, send_selectors: list[str]) -> bool:
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
            continue

    # Enter 键兜底
    try:
        await page.keyboard.press("Enter")
        return True
    except Exception:
        return False


async def _pre_input_deepseek_new_chat(page: Any) -> None:
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
            continue


async def _pre_input_qwen_new_chat(page: Any) -> None:
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
            continue


async def _dismiss_overlays(page: Any, patterns: list[str]) -> None:
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
            continue


async def _upload_image(page: Any, image_path: str) -> bool:
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
            continue
    return False


async def _check_quota(page: Any, patterns: list[str]) -> bool:
    """检查页面文本是否包含限流模式。返回 True 表示配额耗尽。"""
    try:
        body = await page.evaluate("() => document.body.innerText || ''")
    except Exception:
        return False
    for pat in patterns:
        if re.search(pat, body, re.IGNORECASE):
            logger.warning("配额检测命中: %s", pat)
            return True
    return False


async def _get_body_text(page: Any) -> str:
    """获取页面 body 文本。"""
    try:
        return await page.evaluate("() => document.body.innerText || ''")
    except Exception:
        return ""


async def _extract_newest_response(
    page: Any, min_length: int = 5, prev_body: str = ""
) -> str | None:
    """从页面中提取最新的 AI 回复内容。

    策略：
    1. 先用适配器级别的 response_selectors 尝试提取
    2. 在当前 body 中找「提示词之后的新文本」
    3. diff 对比（找最长全新内容行）
    4. 回退到 body 最后几行
    """
    # 1. 尝试适配器级选择器
    try:
        for sel in _current_response_selectors:
            els = await page.query_selector_all(sel)
            if els:
                text = await els[-1].evaluate("el => el.textContent || el.innerText || ''")
                text = (text or "").strip()
                if len(text) >= min_length and not any(
                    n in text for n in ["搜索", "新对话", "复制"]
                ):
                    return text
    except Exception:
        pass

    # 2. 找当前 prompt 在 body 中的位置，取其后的内容
    if _last_prompt:
        try:
            body = await _get_body_text(page)
            idx = body.find(_last_prompt)
            if idx >= 0:
                after = body[idx + len(_last_prompt):].strip()
                lines = [l.strip() for l in after.split("\n") if l.strip()]
                for l in lines:
                    if len(l) >= min_length and not any(
                        n in l for n in ["立即下载", "快捷键", "截屏", "千问快捷"]
                    ):
                        if len(l) >= 15:
                            return l
        except Exception:
            pass

    # 3. Diff 对比
    try:
        current = await _get_body_text(page)
        if current and prev_body:
            prev_lines = set(l.strip() for l in prev_body.split("\n") if l.strip())
            new_lines = [
                l.strip()
                for l in current.split("\n")
                if l.strip()
                and l.strip() not in prev_lines
                and len(l.strip()) >= min_length
            ]
            noise = {
                "搜索", "更多", "新对话", "关闭", "取消", "返回", "复制", "分享",
                "下载", "新建对话", "开始", "确认",
            }
            clean = [
                l for l in new_lines
                if l not in noise
                and len(l) >= 15
                and not any(n in l for n in ["⌘", "⇧", "截图", "下载体验", "快捷键"])
            ]
            if clean:
                return max(clean, key=len)
    except Exception:
        pass

    # 4. 回退
    try:
        body = await _get_body_text(page)
        lines = [l.strip() for l in body.split("\n") if l.strip() and len(l.strip()) >= 15]
        return lines[-1] if lines else None
    except Exception:
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
    page: Any,
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
                                stop_visible = False
                        if stop_visible:
                            break
                except Exception:
                    continue

        if ever_seen_stop and not stop_visible:
            text = await _extract_newest_response(page, min_length=min_len, prev_body=init_body)
            return (text or ""), False

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
    page: Any,
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
                                stop_visible = False
                        if stop_visible:
                            break
                except Exception:
                    continue

        if ever_seen_stop and not stop_visible:
            text = (await _extract_newest_response(page, min_length=min_len, prev_body=init_body)) or ""
            if text != last_yielded:
                yield (text, False)
            return

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


async def _extract_image_urls(page: Any, adapter: dict) -> list[str]:
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


async def _page_healthy(page: Any, adapter: dict[str, Any]) -> bool:
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
        return False


async def run_pipeline(
    page: Any,
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

    if fresh_conversation:
        # ── Step 1: Navigate ──
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            nav_delay = adapter.get("nav_post_delay_ms", 0)
            if nav_delay:
                await asyncio.sleep(nav_delay / 1000.0)
        except Exception as exc:
            return {"success": False, "reason": f"导航失败: {exc}", "provider": name}

        # ── Step 2: Auth check ──
        current_url = page.url
        auth_domains = adapter.get("auth_domains", [])
        if any(d in current_url for d in auth_domains):
            logger.warning("%s 需要登录", name)
            return {"success": False, "reason": "auth", "provider": name}
    else:
        if not await _page_healthy(page, adapter):
            logger.info("%s 页面不健康，回退为新建对话", name)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                nav_delay = adapter.get("nav_post_delay_ms", 0)
                if nav_delay:
                    await asyncio.sleep(nav_delay / 1000.0)
            except Exception as exc:
                return {"success": False, "reason": f"导航失败: {exc}", "provider": name}
            fresh_conversation = True

    # ── Step 3: Quota check ──
    quota_patterns = adapter.get("quota_patterns", [])
    if quota_patterns:
        try:
            if await _check_quota(page, quota_patterns):
                return {"success": False, "reason": "quota", "provider": name}
        except Exception:
            pass

    # ── Step 4: Overlay dismiss ──
    dismiss_patterns = adapter.get("dismiss_patterns", [])
    if dismiss_patterns:
        try:
            await _dismiss_overlays(page, dismiss_patterns)
        except Exception:
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
    page: Any,
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

    yield {"type": "status", "message": f"正在连接 {name}…"}

    if fresh_conversation:
        # ── Step 1: Navigate ──
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            nav_delay = adapter.get("nav_post_delay_ms", 0)
            if nav_delay:
                await asyncio.sleep(nav_delay / 1000.0)
        except Exception as exc:
            yield {"type": "error", "reason": f"导航失败: {exc}", "provider": name}
            return

        # ── Step 2: Auth check ──
        current_url = page.url
        auth_domains = adapter.get("auth_domains", [])
        if any(d in current_url for d in auth_domains):
            logger.warning("%s 需要登录", name)
            yield {"type": "error", "reason": "auth", "provider": name}
            return
    else:
        if not await _page_healthy(page, adapter):
            logger.info("%s 页面不健康，回退为新建对话", name)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                nav_delay = adapter.get("nav_post_delay_ms", 0)
                if nav_delay:
                    await asyncio.sleep(nav_delay / 1000.0)
            except Exception as exc:
                yield {"type": "error", "reason": f"导航失败: {exc}", "provider": name}
                return
            fresh_conversation = True

    # ── Step 3: Quota check ──
    quota_patterns = adapter.get("quota_patterns", [])
    if quota_patterns:
        try:
            if await _check_quota(page, quota_patterns):
                yield {"type": "error", "reason": "quota", "provider": name}
                return
        except Exception:
            pass

    # ── Step 4: Overlay dismiss ──
    dismiss_patterns = adapter.get("dismiss_patterns", [])
    if dismiss_patterns:
        try:
            await _dismiss_overlays(page, dismiss_patterns)
        except Exception:
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
            # 先快速等几秒让 AI 开始生成
            await asyncio.sleep(8)
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
                    pass
                if has_img:
                    break
                # 同时尝试提取文本，但跳过提示词
                raw = await _extract_newest_response(page, min_length=5)
                if raw and _last_prompt and not _normalize_text(_last_prompt) in _normalize_text(raw):
                    response_text = raw
                    yield {"type": "text", "content": response_text}
                await asyncio.sleep(3)
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
