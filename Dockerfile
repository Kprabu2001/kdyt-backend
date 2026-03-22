FROM python:3.12-slim

# ffmpeg for audio transcoding + Node.js for PO token plugin
RUN apt-get update && \
    apt-get install -y ffmpeg curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install yt-dlp PO Token provider plugin (bypasses YouTube bot detection)
RUN pip install --no-cache-dir bgutil-ytdlp-pot-provider

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
