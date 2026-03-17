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
    && ./node_modules/.bin/tsc --skipLibCheck \
    && ls -la /bgutil/server/build/ \
    && test -f /bgutil/server/build/main.js \
    && echo "bgutil build SUCCESS"

# Copy Python packages from builder
COPY --from=builder /install/deps /usr/local

WORKDIR /app
COPY . .

RUN useradd -m appuser \
    && chown -R appuser /app \
    && chown -R appuser /bgutil

USER appuser

EXPOSE 10000

CMD ["sh", "-c", "\
    echo '[startup] Starting bgutil...' && \
    node /bgutil/server/build/main.js & \
    echo '[startup] bgutil PID='$! && \
    sleep 8 && \
    echo '[startup] Starting uvicorn...' && \
    uvicorn main:app --host 0.0.0.0 --port 10000"]