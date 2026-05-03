# ForgeRSS - Docker Image
# Multi-stage build for smaller image

FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip wheel --no-cache-dir --wheel-dir=/app/wheels -r requirements.txt


FROM python:3.11-slim

LABEL maintainer="ForgeRSS Contributors"
LABEL description="Transform any website into RSS feeds"
LABEL version="1.0.0"

WORKDIR /app

# Install runtime dependencies (Chrome/Chromium for Selenium)
# Use Google Chrome on amd64, Chromium on arm64 (Chrome not available for ARM)
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    gnupg \
    && if [ "$TARGETARCH" = "amd64" ]; then \
        wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome-keyring.gpg \
        && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
        && apt-get update \
        && apt-get install -y --no-install-recommends google-chrome-stable; \
    else \
        apt-get install -y --no-install-recommends chromium chromium-driver; \
    fi \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels from builder and install
COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p /app/data /app/cache /app/feeds

# Environment variables with sensible defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOG_LEVEL=INFO \
    MAX_ARTICLES=50 \
    RUN_INTERVAL=21600 \
    FULL_REFRESH=false \
    USE_DB=true

# Volume for persistent data
VOLUME ["/app/data", "/app/cache", "/app/feeds"]

# Health check - 检查进程是否存活
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD pgrep -f "python app.py" || exit 1

# Default: daemon mode (持久运行 + 定时任务)
# 使用 --once 参数可单次运行后退出
CMD ["python", "app.py"]
