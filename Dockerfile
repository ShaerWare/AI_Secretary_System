# =============================================================================
# AI Secretary System - Multi-stage Docker Build
# Supports GPU mode (XTTS + vLLM) and CPU mode (Piper + Gemini)
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Build Vue.js Admin Panel
# -----------------------------------------------------------------------------
FROM node:20-alpine AS admin-builder

WORKDIR /build

# Copy package files first for better caching
COPY admin/package*.json ./
RUN npm ci --silent

# Copy source and build
COPY admin/ ./
RUN npm run build

# -----------------------------------------------------------------------------
# Stage 2: Python Runtime with CUDA
# -----------------------------------------------------------------------------
# Using nvidia/cuda base (smaller, likely cached) + install PyTorch via pip
FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive

# System dependencies + Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3-pip \
    ffmpeg \
    libsndfile1 \
    libportaudio2 \
    git \
    curl \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3

# Install Piper TTS (CPU-based, fast inference for Dmitri/Irina voices)
RUN mkdir -p /opt/piper && cd /opt/piper \
    && wget -q https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz \
    && tar -xzf piper_linux_x86_64.tar.gz \
    && rm piper_linux_x86_64.tar.gz \
    && ln -sf /opt/piper/piper/piper /usr/local/bin/piper

# Install xray-core (for VLESS proxy support with Gemini)
RUN mkdir -p /tmp/xray && cd /tmp/xray \
    && wget -q https://github.com/XTLS/Xray-core/releases/download/v1.8.7/Xray-linux-64.zip \
    && unzip -q Xray-linux-64.zip \
    && mv xray /usr/local/bin/xray \
    && chmod +x /usr/local/bin/xray \
    && rm -rf /tmp/xray

# Download Russian Piper voices (Dmitri + Irina)
RUN mkdir -p /app/models/piper && cd /app/models/piper \
    && wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium.onnx \
    && wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium.onnx.json \
    && wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx \
    && wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx.json

WORKDIR /app

# Create venv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install PyTorch + torchaudio (with pip cache for resume on network issues)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel \
    && pip install torch==2.3.1 torchaudio==2.3.1 \
       --index-url https://download.pytorch.org/whl/cu121

# Install remaining dependencies
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install setuptools wheel \
    && pip install --no-build-isolation openai-whisper==20231117 \
    && pip install -r requirements.txt

# Application code
COPY *.py ./
COPY app/ ./app/
COPY db/ ./db/
COPY telegram_bot/ ./telegram_bot/
COPY whatsapp_bot/ ./whatsapp_bot/
COPY modules/ ./modules/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# CLI-OpenAI Bridge (wraps claude CLI into OpenAI-compatible API)
COPY services/bridge/ ./services/bridge/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install pydantic-settings httpx sse-starlette tiktoken anyio

# Scripts
COPY scripts/ ./scripts/

# Admin panel (from build stage)
COPY --from=admin-builder /build/dist ./admin/dist/

# Voice samples
COPY Анна/ ./Анна/
COPY Марина/ ./Марина/

# Web widget
COPY web-widget/ ./web-widget/

# Create directories for volumes
RUN mkdir -p /app/data /app/logs /app/models /app/temp /app/cache

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV ORCHESTRATOR_PORT=8002
ENV COQUI_TOS_AGREED=1
ENV TTS_CACHE_PATH=/root/.cache/tts_models

# Entrypoint script
COPY scripts/docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose port
EXPOSE 8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "orchestrator.py"]

# -----------------------------------------------------------------------------
# Stage 3: CPU-only variant (smaller image, no CUDA)
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS cpu

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    libportaudio2 \
    git \
    curl \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Piper TTS (CPU-based, fast inference for Dmitri/Irina voices)
RUN mkdir -p /opt/piper && cd /opt/piper \
    && wget -q https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz \
    && tar -xzf piper_linux_x86_64.tar.gz \
    && rm piper_linux_x86_64.tar.gz \
    && ln -sf /opt/piper/piper/piper /usr/local/bin/piper

# Install xray-core (for VLESS proxy support with Gemini)
RUN mkdir -p /tmp/xray && cd /tmp/xray \
    && wget -q https://github.com/XTLS/Xray-core/releases/download/v1.8.7/Xray-linux-64.zip \
    && unzip -q Xray-linux-64.zip \
    && mv xray /usr/local/bin/xray \
    && chmod +x /usr/local/bin/xray \
    && rm -rf /tmp/xray

# Download Russian Piper voices (Dmitri + Irina)
RUN mkdir -p /app/models/piper && cd /app/models/piper \
    && wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium.onnx \
    && wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium.onnx.json \
    && wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx \
    && wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx.json

WORKDIR /app

# Install Python dependencies (CPU versions, uses cache mount)
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel \
    && pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu \
    && grep -v whisper requirements.txt > /tmp/req-cpu.txt && pip install -r /tmp/req-cpu.txt

# Application code
COPY *.py ./
COPY app/ ./app/
COPY db/ ./db/
COPY telegram_bot/ ./telegram_bot/
COPY whatsapp_bot/ ./whatsapp_bot/
COPY modules/ ./modules/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/ ./scripts/

# CLI-OpenAI Bridge
COPY services/bridge/ ./services/bridge/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install pydantic-settings httpx sse-starlette tiktoken anyio

# Admin panel
COPY --from=admin-builder /build/dist ./admin/dist/

# Voice samples
COPY Анна/ ./Анна/
COPY Марина/ ./Марина/

# Web widget
COPY web-widget/ ./web-widget/

# Create directories
RUN mkdir -p /app/data /app/logs /app/models /app/temp /app/cache

# Environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV ORCHESTRATOR_PORT=8002
ENV LLM_BACKEND=gemini

# Entrypoint
COPY scripts/docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "orchestrator.py"]
