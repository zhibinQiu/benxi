"""浏览器 RPA URL 校验测试。"""

import pytest

from app.integrations.browser_automation.url_guard import host_blocked, validate_browser_url


def test_host_blocked_localhost():
    assert host_blocked("localhost") is True
    assert host_blocked("127.0.0.1") is True


def test_validate_browser_url_public():
    url = validate_browser_url("https://example.com/path")
    assert url.startswith("https://example.com")


def test_validate_browser_url_rejects_file_scheme():
    with pytest.raises(ValueError, match="http"):
        validate_browser_url("file:///etc/passwd")


def test_validate_browser_url_domain_allowlist():
    with pytest.raises(ValueError, match="白名单"):
        validate_browser_url(
            "https://evil.com",
            allowed_domains="example.com",
        )
    ok = validate_browser_url(
        "https://sub.example.com/x",
        allowed_domains="example.com",
    )
    assert "example.com" in ok
