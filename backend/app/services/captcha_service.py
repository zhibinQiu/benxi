"""文字验证码服务 — 后端生成 4 字符图片验证码，前端输入验证。

存储层同时支持 Redis（多 Worker 共享）和进程内内存（降级）。
"""

from __future__ import annotations

import base64
import io
import secrets
import time
import uuid

from app.core.redis_client import get_redis_client

# ── Redis key 前缀 ──────────────────────────────
_CAPTCHA_KEY_PREFIX = "captcha:"
_VERIFIED_KEY_PREFIX = "verified:"

# ── Token（滑块+文字验证码共用） ───────────────────────────

VERIFIED_TTL_SEC = 120

_VERIFIED: dict[str, float] = {}
_CLEANUP_THRESHOLD = 100


def _verified_store(token: str) -> None:
    """保存已验证 token 到共享存储。"""
    client = get_redis_client()
    if client is not None:
        client.setex(f"{_VERIFIED_KEY_PREFIX}{token}", VERIFIED_TTL_SEC, "1")
        return
    # Fallback: 进程内存
    if len(_VERIFIED) >= _CLEANUP_THRESHOLD:
        now = time.time()
        for t, ts in list(_VERIFIED.items()):
            if now - ts > VERIFIED_TTL_SEC:
                del _VERIFIED[t]
    _VERIFIED[token] = time.time()


def _consume_verified(token: str) -> bool:
    """消耗已验证 token，成功返回 True。"""
    client = get_redis_client()
    if client is not None:
        return client.delete(f"{_VERIFIED_KEY_PREFIX}{token}") > 0
    # Fallback: 进程内存
    ts = _VERIFIED.pop(token, None)
    if ts is None:
        return False
    if time.time() - ts > VERIFIED_TTL_SEC:
        return False
    return True


# ── 文字验证码 ─────────────────────────────────────

CAPTCHA_TTL_SEC = 300
CAPTCHA_CLEANUP_THRESHOLD = 200

_CAPTCHAS: dict[str, dict] = {}

# 排除易混淆字符：0/O、1/I/L/l、S/5、B/8
CAPTCHA_CHARS = "234679ABCDEFGHJKMNPQRTUVWXYZabcdefghjkmnpqrtuvwxyz"


def _store_captcha(captcha_id: str, code: str) -> None:
    """保存验证码到共享存储。"""
    client = get_redis_client()
    if client is not None:
        client.setex(f"{_CAPTCHA_KEY_PREFIX}{captcha_id}", CAPTCHA_TTL_SEC, code)
        return
    # Fallback: 进程内存
    if len(_CAPTCHAS) >= CAPTCHA_CLEANUP_THRESHOLD:
        now = time.time()
        for cid, data in list(_CAPTCHAS.items()):
            if now - data["ts"] > CAPTCHA_TTL_SEC:
                del _CAPTCHAS[cid]
    _CAPTCHAS[captcha_id] = {"code": code, "ts": time.time()}


def _pop_captcha(captcha_id: str) -> str | None:
    """取出并删除验证码。返回 code 或 None。"""
    client = get_redis_client()
    if client is not None:
        key = f"{_CAPTCHA_KEY_PREFIX}{captcha_id}"
        pipe = client.pipeline()
        pipe.get(key)
        pipe.delete(key)
        results = pipe.execute()
        return results[0]  # GET 返回 None 或 code 字符串
    # Fallback: 进程内存
    data = _CAPTCHAS.pop(captcha_id, None)
    if data is None:
        return None
    if time.time() - data["ts"] > CAPTCHA_TTL_SEC:
        return None
    return data["code"]


def _random_color(low: int = 40, high: int = 200) -> tuple[int, int, int]:
    return (
        secrets.randbelow(high - low) + low,
        secrets.randbelow(high - low) + low,
        secrets.randbelow(high - low) + low,
    )


def _draw_text_captcha(code: str) -> str:
    """生成 4 字符验证码图片，返回 data URI (base64 PNG)。"""
    from PIL import Image, ImageDraw, ImageFont

    width, height = 240, 80
    image = Image.new("RGB", (width, height), (248, 249, 250))
    draw = ImageDraw.Draw(image)

    # 尝试多种字体路径（容器部署可用 fonts-wqy-microhei / fonts-dejavu-core）
    font = None
    for fp in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ):
        try:
            font = ImageFont.truetype(fp, 40)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()

    char_count = len(code)
    total_width = width - 30
    char_step = total_width // char_count

    for i, ch in enumerate(code):
        angle = secrets.randbelow(50) - 25
        color = _random_color(30, 180)
        x = 15 + i * char_step + secrets.randbelow(10)
        y = secrets.randbelow(20) + 5

        char_img = Image.new("RGBA", (50, 60), (0, 0, 0, 0))
        char_draw = ImageDraw.Draw(char_img)
        char_draw.text((5, 5), ch, fill=(*color, 255), font=font)
        rotated = char_img.rotate(angle, expand=1, fillcolor=(0, 0, 0, 0))
        image.paste(rotated, (x, y), rotated)

    # 干扰线
    for _ in range(4):
        c = _random_color(140, 210)
        x1 = secrets.randbelow(width)
        y1 = secrets.randbelow(height)
        x2 = secrets.randbelow(width)
        y2 = secrets.randbelow(height)
        draw.line([(x1, y1), (x2, y2)], fill=c, width=secrets.randbelow(2) + 1)

    # 干扰点
    for _ in range(60):
        c = _random_color(130, 220)
        draw.point(
            (secrets.randbelow(width), secrets.randbelow(height)),
            fill=c,
        )

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def generate_text_captcha() -> tuple[str, str]:
    """生成 4 字符验证码，返回 (captcha_id, base64_image_data_uri)。"""
    code = "".join(secrets.choice(CAPTCHA_CHARS) for _ in range(4))
    captcha_id = str(uuid.uuid4())
    _store_captcha(captcha_id, code)
    image = _draw_text_captcha(code)
    return captcha_id, image


def verify_text_captcha(captcha_id: str, answer: str) -> str | None:
    """校验文字验证码。成功返回 token，失败返回 None。"""
    code = _pop_captcha(captcha_id)
    if code is None:
        return None
    if code.lower() != answer.strip().lower():
        return None
    return issue_token()


# ── 公开 API（兼容旧导入） ────────────────────────


def issue_token() -> str:
    """前端验证码通过后，颁发一个短期有效的验证 token。"""
    token = secrets.token_hex(16)
    _verified_store(token)
    return token


def consume_verified(token: str) -> bool:
    """消耗一个已验证的 token（登录/注册时调用）。"""
    return _consume_verified(token)
