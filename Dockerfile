# Dockerfile
# Multi-stage build — keeps the final image lean.

# ── Stage 1: dependency install ────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /install

COPY requirements.txt .
RUN pip install --prefix=/install/deps --no-cache-dir -r requirements.txt


# ── Stage 2: runtime ───────────────────────────────────────────────
FROM python:3.12-slim

# System deps: ffmpeg (required for merging video+audio streams)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install yt-dlp binary (kept separate so it can be updated without rebuilding)
RUN pip install --no-cache-dir yt-dlp

# Copy installed Python packages from builder
COPY --from=builder /install/deps /usr/local

WORKDIR /app
COPY . .

# Non-root user for security
RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
