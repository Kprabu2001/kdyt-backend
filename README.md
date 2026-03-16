# SwiftDL — Backend

FastAPI backend for the SwiftDL YouTube downloader.

---

## Project Structure

```
swiftdl-backend/
│
├── main.py                        App factory — wires everything together
├── requirements.txt
├── pytest.ini
├── Dockerfile
├── .env.example
│
├── app/
│   │
│   ├── api/                       HTTP layer — nothing here touches yt-dlp directly
│   │   ├── router.py              Assembles all endpoint routers into one
│   │   ├── middleware.py          SecurityHeadersMiddleware (X-Frame-Options, etc.)
│   │   └── endpoints/
│   │       ├── health.py          GET /api/health
│   │       ├── info.py            GET /api/info    — fetch video metadata + formats
│   │       └── download.py        GET /api/download — stream MP4 or MP3
│   │
│   ├── core/                      App-wide singletons
│   │   ├── config.py              Pydantic Settings — all env vars in one place
│   │   └── limiter.py             slowapi Limiter singleton
│   │
│   ├── models/
│   │   └── video.py               Pydantic schemas: VideoInfo, VideoFormat, HealthResponse
│   │
│   ├── services/
│   │   └── ytdlp.py               All yt-dlp subprocess calls (info, stream_video, stream_audio)
│   │
│   └── utils/
│       ├── validators.py          is_valid_youtube_url()
│       └── formatters.py          format_duration / format_views / format_filesize / sanitize_filename
│
└── tests/
    ├── test_validators.py         Unit tests — URL validation
    ├── test_formatters.py         Unit tests — formatting helpers
    └── test_api.py                Integration tests — endpoints (services mocked)
```

---

## Quick Start

### 1. System requirements

```bash
# Ubuntu / Debian
sudo apt install python3.12 ffmpeg -y

# macOS
brew install python@3.12 ffmpeg

# Install yt-dlp (keep updated — YouTube changes its API frequently)
pip install yt-dlp
# or:
sudo curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
     -o /usr/local/bin/yt-dlp && sudo chmod +x /usr/local/bin/yt-dlp
```

### 2. Install Python dependencies

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env — at minimum set ALLOWED_ORIGINS to your frontend URL
```

### 4. Run (development)

```bash
uvicorn main:app --port 8000 --reload
```

| URL | Description |
|-----|-------------|
| http://localhost:8000/api/docs    | Swagger UI — interactive API explorer |
| http://localhost:8000/api/redoc   | ReDoc — clean API reference |
| http://localhost:8000/api/health  | Health check endpoint |

---

## API Reference

### `GET /api/health`
Returns `{ "status": "ok" }`. Used by load balancers and uptime monitors.

---

### `GET /api/info`

| Parameter | Type   | Required | Description              |
|-----------|--------|----------|--------------------------|
| `url`     | string | ✅       | Full YouTube video URL   |

**Response** `200 VideoInfo`:
```json
{
  "title":    "Never Gonna Give You Up",
  "channel":  "Rick Astley",
  "thumbnail": "https://i.ytimg.com/...",
  "duration": "3:33",
  "views":    "1.4B",
  "video_formats": [
    { "format_id": "137", "quality": "1080p", "ext": "mp4", "filesize": "128 MB" }
  ],
  "audio_formats": [
    { "format_id": "320kbps", "quality": "320 kbps", "ext": "mp3", "filesize": null }
  ]
}
```

**Rate limit:** 30 requests / 15 minutes / IP

---

### `GET /api/download`

| Parameter   | Type                  | Required | Description                          |
|-------------|-----------------------|----------|--------------------------------------|
| `url`       | string                | ✅       | Full YouTube video URL               |
| `format_id` | string                | ✅       | `format_id` from `/api/info` response |
| `type`      | `"video"` \| `"audio"` | ✅      | Download type                        |

Streams the file directly. The browser receives a `Content-Disposition: attachment` header and triggers a Save dialog.

**Rate limit:** 10 downloads / hour / IP

---

## Running Tests

```bash
pytest -v
# Or with coverage:
pip install pytest-cov
pytest --cov=app --cov-report=term-missing
```

---

## Production Deployment

### With PM2

```bash
pip install -r requirements.txt
pm2 start "uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2" \
    --name swiftdl-api
pm2 save && pm2 startup
```

### With Docker

```bash
docker build -t swiftdl-api .
docker run -d -p 8000:8000 \
  -e ALLOWED_ORIGINS="https://yourdomain.com" \
  --name swiftdl \
  swiftdl-api
```

### Nginx reverse proxy (abridged)

```nginx
location /api/ {
    proxy_pass         http://127.0.0.1:8000;
    proxy_buffering    off;          # critical for streaming downloads
    proxy_read_timeout 600s;
    proxy_send_timeout 600s;
}
```

---

## Keep yt-dlp Updated

YouTube changes its internal API frequently. Update yt-dlp weekly:

```bash
# Manual
yt-dlp -U

# Cron (every Sunday at 3 AM)
0 3 * * 0 /usr/local/bin/yt-dlp -U >> /var/log/yt-dlp-update.log 2>&1
```
