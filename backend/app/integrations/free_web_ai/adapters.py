"""Provider 适配器配置 — 每个 provider 的差异通过数据表达，非重复代码。

每个 adapter 定义:
- url / auth_domains: 导航与登录检测
- editor_selectors / send_selectors: 操作 DOM 选择器（引擎会自动兜底）
- quota_patterns: 限流检测正则
- 特殊行为钩子: pre_input, post_response 等
- 图片能力: supports_image_upload / supports_image_gen
"""

from __future__ import annotations

from typing import Any

# ── 公共模式 ──
COMMON_CN_QUOTA_PATTERNS = [
    r"额度.*(?:已|用).*(?:完|尽|满)",
    r"quota\s*(?:exceeded|limit)",
    r"次数.*(?:已|用).*(?:完|尽)",
    r"请.*(?:充值|升级|续费)",
    r"rate\s*limit",
    r"too\s*many\s*requests",
    r"免费.*次数.*已.*用完",
    r"今日.*已.*用.*完",
]

COMMON_DISMISS_PATTERNS = [
    r"新功能",
    r"公告",
    r"欢迎",
    r"更新.*(?:说明|日志)",
    r"what'?s\s*new",
    r"new\s*feature",
    r"welcome",
    r"try\s*(?:the\s*)?new",
    r"introducing",
]


def _default_quota_patterns() -> list[str]:
    return list(COMMON_CN_QUOTA_PATTERNS)


def _default_dismiss_patterns() -> list[str]:
    return list(COMMON_DISMISS_PATTERNS)


# ── Provider Adapter 定义 ──

DOUBAO: dict[str, Any] = {
    "key": "doubao",
    "name": "豆包",
    "url": "https://www.doubao.com/chat/",
    "auth_domains": ["doubao.com/login", "login.doubao.com"],
    "nav_post_delay_ms": 4000,
    "quota_patterns": _default_quota_patterns(),
    "dismiss_patterns": _default_dismiss_patterns() + [r"新功能.*介绍", r"首次.*使用"],
    "editor_selectors": [
        "[class*='chat-input'] textarea",
        "textarea[class*='input']",
        "textarea[placeholder*='输入']",
        "textarea",
        '[contenteditable="true"]',
        '[role="textbox"]',
    ],
    "send_selectors": [
        "[class*='send-button']",
        "[class*='submit-btn']",
        'button[aria-label*="发送"]',
        "button[class*='send']",
    ],
    "stop_selectors": [
        "button[class*='stop']",
        "[class*='stop-btn']",
        "[class*='stop-generating']",
    ],
    "stop_wait_mode": "detached",
    "response_selectors": [
        "[class*='ds-message-content']",
        "[class*='ds-chat-message-role-assistant']",
        ".ds-markdown",
        "[class*='message-bubble']",
        "[class*='assistant-message']",
        "[class*='answer-content']",
    ],
    "extract_patterns": [
        r"由\s*#.*(?:AI|免费).*生成",
        r"搜索.*关键词.*参考.*资料",
        r"Powered by.*",
    ],
    "stability_window_ms": 10000,
    "min_response_length": 5,
    "supports_image_upload": True,
    "supports_image_gen": True,
    "upload_selector_hint": 'input[type="file"], button[aria-label*="图片"]',
    "image_gen_prefix": "帮我画一张图: ",
}

QWEN: dict[str, Any] = {
    "key": "qwen",
    "name": "通义千问",
    "url": "https://www.qianwen.com/",
    "auth_domains": ["login.aliyun.com", "signin.aliyun.com"],
    "nav_post_delay_ms": 3000,
    "quota_patterns": _default_quota_patterns(),
    "dismiss_patterns": _default_dismiss_patterns() + [r"提示", r"体验"],
    "pre_input_hook": "qwen_new_chat",
    "editor_selectors": [
        '[contenteditable="true"][role="textbox"]',
        '[contenteditable="true"]',
        "textarea",
        '[role="textbox"]',
    ],
    "send_selectors": [
        "button[aria-label*='发送']",
        "button[aria-label='发送消息']",
    ],
    "response_selectors": [
    ],
    "extract_patterns": [
        "你好.*?(?:千问|AI)",
        "我是千问.*",
    ],
    "stability_window_ms": 8000,
    "min_response_length": 5,
    "supports_image_upload": True,
    "supports_image_gen": True,
    "upload_selector_hint": 'input[type="file"][accept*="image"], button[aria-label*="图片"]',
    "image_gen_prefix": "使用通义万相画图: ",
}

DEEPSEEK: dict[str, Any] = {
    "key": "deepseek",
    "name": "DeepSeek",
    "url": "https://chat.deepseek.com/",
    "auth_domains": ["chat.deepseek.com/login", "deepseek.com/login"],
    "nav_post_delay_ms": 3000,
    "quota_patterns": _default_quota_patterns(),
    "dismiss_patterns": _default_dismiss_patterns() + [r"更新.*公告", r"新版本"],
    "pre_input_hook": "deepseek_new_chat",
    "editor_selectors": [
        "textarea[placeholder*='给 DeepSeek 发送消息']",
        "textarea[placeholder*='DeepSeek']",
        "textarea",
    ],
    "send_selectors": [
        "button[class*='send']",
        "button[class*='submit']",
    ],
    "response_selectors": [
        ".ds-markdown",
        ".ds-assistant-message-main-content",
        "[class*='message-content']",
    ],
    "stability_window_ms": 12000,
    "min_response_length": 5,
    "supports_image_upload": True,
    "supports_image_gen": False,
    "upload_selector_hint": 'input[type="file"], button[aria-label*="上传"]',
}


# ── Provider 链 ──

PROVIDER_CHAIN = [
    QWEN,
    DOUBAO,
    DEEPSEEK,
]

ADAPTER_MAP: dict[str, dict[str, Any]] = {
    "doubao": DOUBAO,
    "qwen": QWEN,
    "deepseek": DEEPSEEK,
}


def get_adapter(key: str) -> dict[str, Any] | None:
    return ADAPTER_MAP.get(key.lower().strip())
