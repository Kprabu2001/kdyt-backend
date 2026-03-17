# ── Stage 1: dependency install ────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /install
COPY requirements.txt .
RUN pip install --prefix=/install/deps --no-cache-dir -r requirements.txt

# ── Stage 2: runtime ───────────────────────────────────────────────
FROM python:3.12-slim

# System deps: ffmpeg + Node.js (required for bgutil POT server)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg curl gnupg ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install latest yt-dlp
RUN pip install --no-cache-dir --upgrade yt-dlp

# Install bgutil-ytdlp-pot-provider plugin for yt-dlp
RUN pip install --no-cache-dir bgutil-ytdlp-pot-provider

# Clone and build bgutil HTTP server
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && git clone --single-branch --branch 1.3.1 \
       https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git \
       /bgutil \
    && cd /bgutil/server && npm ci && npx tsc \
    && apt-get remove -y git && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install/deps /usr/local

WORKDIR /app
COPY . .

RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Start bgutil POT server on port 4416, then start FastAPI
CMD ["sh", "-c", "node /bgutil/server/build/main.js &  yt-dlp -U && uvicorn main:app --host 0.0.0.0 --port 10000"]