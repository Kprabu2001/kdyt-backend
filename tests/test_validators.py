# tests/test_validators.py
# Unit tests for app/utils/validators.py
# Run: pytest tests/test_validators.py -v

import pytest
from app.utils.validators import is_valid_youtube_url


# ── Valid URLs ─────────────────────────────────────────────────────
@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ",
    "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
    "http://www.youtube.com/watch?v=abc123",           # http is allowed
    "https://www.youtube.com/watch?v=abc&list=PLxxx",  # with playlist param
])
def test_valid_youtube_urls(url):
    assert is_valid_youtube_url(url) is True


# ── Invalid URLs ───────────────────────────────────────────────────
@pytest.mark.parametrize("url", [
    "https://vimeo.com/123456",
    "https://evil.com/youtube.com/watch?v=abc",  # path trick
    "https://youtube.com.evil.com/watch?v=abc",  # subdomain trick
    "https://notyoutube.com/watch?v=abc",
    "ftp://youtube.com/watch?v=abc",             # wrong scheme
    "javascript:alert(1)",                       # XSS attempt
    "not-a-url",
    "",
    "   ",
])
def test_invalid_youtube_urls(url):
    assert is_valid_youtube_url(url) is False


# ── Edge cases ─────────────────────────────────────────────────────
def test_none_returns_false():
    # Should not raise, should return False
    assert is_valid_youtube_url(None) is False  # type: ignore[arg-type]


def test_very_long_string_does_not_raise():
    assert is_valid_youtube_url("x" * 10_000) is False
