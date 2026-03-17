# ── Stage 1: Python dependency install ─────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /install
COPY requirements.txt .
RUN pip install --prefix=/install/deps --no-cache-dir -r requirements.txt


# ── Stage 2: runtime ───────────────────────────────────────────────
FROM python:3.12-slim

# System deps: ffmpeg + Node.js
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ffmpeg curl gnupg ca-certificates git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install yt-dlp + bgutil plugin
RUN pip install --no-cache-dir --upgrade yt-dlp bgutil-ytdlp-pot-provider

# Clone and build bgutil HTTP server
RUN git clone --depth 1 --branch 1.3.1 \
    https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /bgutil \
    && cd /bgutil/server \
    && npm ci \
    && npx tsc --skipLibCheck

# Copy Python packages from builder
COPY --from=builder /install/deps /usr/local

WORKDIR /app
COPY . .

# Remove any local cookies.txt so secrets never end up in the image.
# Cookies are injected at runtime via YTDLP_COOKIES_B64 env var.
RUN rm -f /app/cookies.txt

RUN useradd -m appuser \
    && chown -R appuser /app \
    && chown -R appuser /bgutil \
    # Ensure appuser can write to /tmp for runtime cookie file
    && chmod 1777 /tmp

USER appuser

EXPOSE 10000

# Env vars to set on Render (do NOT hardcode secrets here):
#   YTDLP_COOKIES_B64          — base64-encoded cookies.txt content
#   COOKIE_REFRESH_INTERVAL    — seconds between auto-refresh (default 3600)

CMD ["sh", "-c", "\
    node /bgutil/server/build/main.js & \
    sleep 3 && \
    yt-dlp -U --quiet && \
    uvicorn main:app --host 0.0.0.0 --port 10000"]