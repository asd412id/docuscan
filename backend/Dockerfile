# ===========================================
# DocuScan Backend - Production Dockerfile
# Multi-stage build for optimized image size
# ===========================================

# Build arguments
ARG PYTHON_VERSION=3.11
ARG TESSERACT_LANGUAGES="eng ind"
ARG UVICORN_WORKERS=2

# ===========================================
# Stage 1: Builder
# ===========================================
FROM python:${PYTHON_VERSION}-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ===========================================
# Stage 2: Production
# ===========================================
FROM python:${PYTHON_VERSION}-slim as production

# Re-declare ARGs for this stage
ARG TESSERACT_LANGUAGES="eng ind"
ARG UVICORN_WORKERS=2

# Labels
LABEL maintainer="DocuScan Team"
LABEL description="DocuScan Backend API"
LABEL version="1.0.0"

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PATH="/opt/venv/bin:$PATH" \
    UVICORN_WORKERS=${UVICORN_WORKERS}

# Install runtime dependencies
# Note: libgl1-mesa-glx is deprecated in Debian Trixie+, use libgl1 instead
RUN apt-get update && apt-get install -y --no-install-recommends \
    # OpenCV dependencies (libgl1 replaces libgl1-mesa-glx in newer Debian)
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    # Tesseract OCR base
    tesseract-ocr \
    # Health check
    curl \
    # Clean up
    && rm -rf /var/lib/apt/lists/*

# Install Tesseract language packs dynamically
RUN for lang in ${TESSERACT_LANGUAGES}; do \
        if [ "$lang" != "eng" ]; then \
            apt-get update && apt-get install -y --no-install-recommends tesseract-ocr-${lang} || true; \
        fi; \
    done && \
    apt-get install -y --no-install-recommends tesseract-ocr-eng && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY --chown=appuser:appgroup . .

# Create upload directory with proper permissions
RUN mkdir -p /app/uploads && \
    chown -R appuser:appgroup /app/uploads

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Note: Healthcheck defined in docker-compose.yml because backend and celery-worker
# share this image but have different health check requirements

# Run application with configurable workers
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-2}"]
