# ── Stage 1: Python dependency install ─────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /install
COPY requirements.txt .
RUN pip install --prefix=/install/deps --no-cache-dir -r requirements.txt


# ── Stage 2: runtime ───────────────────────────────────────────────
FROM python:3.12-slim

# System deps: ffmpeg + Node.js (for bgutil POT server)
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
    && npm run build

# Copy Python packages from builder
COPY --from=builder /install/deps /usr/local

WORKDIR /app
COPY . .

# Give appuser access to bgutil too
RUN useradd -m appuser \
    && chown -R appuser /app \
    && chown -R appuser /bgutil

USER appuser

EXPOSE 10000

# Start bgutil, wait for it to be ready, then start FastAPI
CMD ["sh", "-c", "\
    node /bgutil/server/build/main.js & \
    sleep 3 && \
    yt-dlp -U --quiet && \
    uvicorn main:app --host 0.0.0.0 --port 10000"]