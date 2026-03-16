# tests/test_api.py
# Integration tests for the FastAPI endpoints.
# Uses httpx TestClient — no real yt-dlp calls are made (services are mocked).
# Run: pytest tests/test_api.py -v

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from app.models.video import VideoFormat, VideoInfo

client = TestClient(app)

# ── Fixtures ───────────────────────────────────────────────────────

MOCK_VIDEO_INFO = VideoInfo(
    title="Test Video",
    channel="Test Channel",
    thumbnail="https://i.ytimg.com/vi/abc/hqdefault.jpg",
    duration="3:45",
    views="1.2M",
    video_formats=[
        VideoFormat(format_id="137", quality="1080p",  ext="mp4", filesize="128 MB"),
        VideoFormat(format_id="136", quality="720p",   ext="mp4", filesize="64 MB"),
        VideoFormat(format_id="135", quality="480p",   ext="mp4", filesize="32 MB"),
    ],
    audio_formats=[
        VideoFormat(format_id="320kbps", quality="320 kbps", ext="mp3"),
        VideoFormat(format_id="192kbps", quality="192 kbps", ext="mp3"),
        VideoFormat(format_id="128kbps", quality="128 kbps", ext="mp3"),
    ],
)

VALID_URL   = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
INVALID_URL = "https://vimeo.com/123456"


# ── Health check ───────────────────────────────────────────────────
class TestHealthCheck:
    def test_returns_200(self):
        res = client.get("/api/health")
        assert res.status_code == 200

    def test_returns_ok_status(self):
        res = client.get("/api/health")
        assert res.json() == {"status": "ok"}


# ── GET /api/info ──────────────────────────────────────────────────
class TestGetInfo:
    def test_rejects_missing_url(self):
        res = client.get("/api/info")
        assert res.status_code == 422  # FastAPI validation error

    def test_rejects_invalid_url(self):
        res = client.get(f"/api/info?url={INVALID_URL}")
        assert res.status_code == 400
        assert "YouTube" in res.json()["detail"]

    def test_rejects_empty_url(self):
        res = client.get("/api/info?url=")
        assert res.status_code == 400

    @patch("app.api.endpoints.info.ytdlp.get_video_info", new_callable=AsyncMock)
    def test_returns_video_info_on_success(self, mock_get_info):
        mock_get_info.return_value = MOCK_VIDEO_INFO
        res = client.get(f"/api/info?url={VALID_URL}")
        assert res.status_code == 200
        data = res.json()
        assert data["title"]   == "Test Video"
        assert data["channel"] == "Test Channel"
        assert len(data["video_formats"]) == 3
        assert len(data["audio_formats"]) == 3

    @patch("app.api.endpoints.info.ytdlp.get_video_info", new_callable=AsyncMock)
    def test_returns_502_on_ytdlp_runtime_error(self, mock_get_info):
        mock_get_info.side_effect = RuntimeError("yt-dlp error")
        res = client.get(f"/api/info?url={VALID_URL}")
        assert res.status_code == 502

    @patch("app.api.endpoints.info.ytdlp.get_video_info", new_callable=AsyncMock)
    def test_returns_400_for_private_video(self, mock_get_info):
        mock_get_info.side_effect = RuntimeError("Private video")
        res = client.get(f"/api/info?url={VALID_URL}")
        assert res.status_code == 400
        assert "private" in res.json()["detail"].lower()


# ── GET /api/download ──────────────────────────────────────────────
class TestDownload:
    def test_rejects_invalid_url(self):
        res = client.get(
            f"/api/download?url={INVALID_URL}&format_id=137&type=video",
            follow_redirects=False,
        )
        assert res.status_code == 400

    def test_rejects_invalid_type(self):
        res = client.get(
            f"/api/download?url={VALID_URL}&format_id=137&type=invalid",
        )
        assert res.status_code == 422  # pattern validation failure

    def test_rejects_missing_params(self):
        res = client.get(f"/api/download?url={VALID_URL}")
        assert res.status_code == 422
