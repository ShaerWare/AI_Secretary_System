# CLI-OpenAI Bridge: Python API + the CLI tools it wraps (Node-based).
FROM node:22-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

# CLIs. Shell-GPT is optional: add `shell-gpt` to the pip line and set OPENAI_API_KEY.
RUN npm install -g @anthropic-ai/claude-code @google/gemini-cli \
    && npm cache clean --force

WORKDIR /app
COPY requirements.txt .
RUN python3 -m venv /venv \
    && /venv/bin/pip install --no-cache-dir -r requirements.txt
ENV PATH="/venv/bin:$PATH" \
    BRIDGE_HOST=0.0.0.0 \
    BRIDGE_PORT=8000

COPY src ./src

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["python3", "-m", "src.server.main"]
