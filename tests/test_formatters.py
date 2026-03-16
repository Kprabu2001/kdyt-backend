# tests/test_formatters.py
# Unit tests for app/utils/formatters.py
# Run: pytest tests/test_formatters.py -v

import pytest
from app.utils.formatters import (
    format_duration,
    format_filesize,
    format_views,
    sanitize_filename,
)


# ── format_duration ────────────────────────────────────────────────
class TestFormatDuration:
    def test_none_returns_zero(self):
        assert format_duration(None) == "0:00"

    def test_zero_returns_zero(self):
        assert format_duration(0) == "0:00"

    def test_seconds_only(self):
        assert format_duration(45) == "0:45"

    def test_single_digit_seconds_padded(self):
        assert format_duration(61) == "1:01"

    def test_minutes_and_seconds(self):
        assert format_duration(125) == "2:05"

    def test_exactly_one_hour(self):
        assert format_duration(3600) == "1:00:00"

    def test_hours_minutes_seconds(self):
        assert format_duration(3661) == "1:01:01"

    def test_large_value(self):
        assert format_duration(7322) == "2:02:02"


# ── format_views ───────────────────────────────────────────────────
class TestFormatViews:
    def test_none_returns_zero_string(self):
        assert format_views(None) == "0"

    def test_zero_returns_zero_string(self):
        assert format_views(0) == "0"

    def test_below_thousand(self):
        assert format_views(800) == "800"

    def test_exactly_one_thousand(self):
        assert format_views(1_000) == "1.0K"

    def test_thousands(self):
        assert format_views(12_500) == "12.5K"

    def test_exactly_one_million(self):
        assert format_views(1_000_000) == "1.0M"

    def test_millions(self):
        assert format_views(1_500_000) == "1.5M"

    def test_large_millions(self):
        assert format_views(123_456_789) == "123.5M"


# ── format_filesize ────────────────────────────────────────────────
class TestFormatFilesize:
    def test_none_returns_none(self):
        assert format_filesize(None) is None

    def test_zero_returns_none(self):
        assert format_filesize(0) is None

    def test_bytes(self):
        assert format_filesize(512) == "512 B"

    def test_kilobytes(self):
        assert format_filesize(2_048) == "2 KB"

    def test_megabytes(self):
        assert format_filesize(52_428_800) == "50 MB"

    def test_gigabytes(self):
        assert format_filesize(1_073_741_824) == "1.0 GB"

    def test_large_gigabytes(self):
        result = format_filesize(3_221_225_472)  # 3 GB
        assert result == "3.0 GB"


# ── sanitize_filename ──────────────────────────────────────────────
class TestSanitizeFilename:
    def test_clean_title_unchanged(self):
        assert sanitize_filename("Rick Astley - Never Gonna Give You Up") == \
               "Rick Astley - Never Gonna Give You Up"

    def test_removes_slashes(self):
        result = sanitize_filename("Video / Part 1")
        assert "/" not in result

    def test_removes_angle_brackets(self):
        result = sanitize_filename("Title <official>")
        assert "<" not in result
        assert ">" not in result

    def test_empty_string_returns_download(self):
        assert sanitize_filename("") == "download"

    def test_only_special_chars_returns_download(self):
        assert sanitize_filename("!@#$%^&*()") == "download"

    def test_truncates_to_80_chars(self):
        long_title = "A" * 200
        assert len(sanitize_filename(long_title)) <= 80

    def test_strips_surrounding_whitespace(self):
        assert sanitize_filename("  My Video  ") == "My Video"
