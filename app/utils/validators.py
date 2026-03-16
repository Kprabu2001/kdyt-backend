# app/utils/validators.py
# Input validation helpers.
# Pure functions — no I/O, no side effects, easily unit-tested.

from urllib.parse import urlparse

# Only these exact hostnames are accepted.
# Subdomains beyond "www." and "m." are intentionally excluded.
_VALID_YT_HOSTS: frozenset[str] = frozenset({
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
    "m.youtube.com",
})


def is_valid_youtube_url(url: str) -> bool:
    """
    Return True if `url` is a well-formed http/https YouTube URL.

    Rejects:
    - Non-YouTube domains (vimeo.com, etc.)
    - Subdomain tricks (evil.com/youtube.com)
    - Non-http schemes (javascript:, data:, etc.)
    - Malformed or empty strings
    """
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme in ("http", "https")
            and bool(parsed.hostname)
            and parsed.hostname in _VALID_YT_HOSTS
        )
    except Exception:
        return False
