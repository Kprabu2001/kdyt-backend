# app/utils/formatters.py
# Pure formatting helpers — no I/O, no side effects, easily unit-tested.
# All functions accept Optional inputs and return safe defaults on None/0.

import re
from typing import Optional


def format_duration(seconds: Optional[int]) -> str:
    """
    Convert a raw seconds integer into a human-readable time string.

    Examples:
        45    → "0:45"
        125   → "2:05"
        3661  → "1:01:01"
        None  → "0:00"
    """
    if not seconds:
        return "0:00"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_views(n: Optional[int]) -> str:
    """
    Abbreviate a raw view count into a short human-readable string.

    Examples:
        1_500_000 → "1.5M"
        12_500    → "12.5K"
        800       → "800"
        None      → "0"
    """
    if not n:
        return "0"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def format_filesize(bytes_: Optional[int]) -> Optional[str]:
    """
    Convert a raw byte count into a human-readable size string.
    Returns None when the size is unknown (yt-dlp may not always provide it).

    Examples:
        1_073_741_824 → "1.0 GB"
        52_428_800    → "50 MB"
        2_048         → "2 KB"
        None          → None
    """
    if not bytes_:
        return None
    if bytes_ >= 1_073_741_824:
        return f"{bytes_ / 1_073_741_824:.1f} GB"
    if bytes_ >= 1_048_576:
        return f"{bytes_ / 1_048_576:.0f} MB"
    if bytes_ >= 1_024:
        return f"{bytes_ / 1_024:.0f} KB"
    return f"{bytes_} B"


def sanitize_filename(title: str) -> str:
    """
    Strip characters unsafe for Content-Disposition filenames and cap length.

    Keeps: word chars, spaces, hyphens.
    Removes: everything else (slashes, quotes, angle brackets, etc.)

    Examples:
        "Rick Astley - Never Gonna Give You Up" → "Rick Astley - Never Gonna Give You Up"
        "Video <title> / part 1"               → "Video title  part 1"
        ""                                     → "download"
    """
    clean = re.sub(r"[^\w\s\-]", "", title)
    result = clean.strip()[:80]
    return result or "download"
