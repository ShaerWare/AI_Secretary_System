#!/bin/bash
# CLI-OpenAI Bridge Server Starter (Linux/macOS)

cd "$(dirname "$0")"

# Ensure ~/.local/bin is in PATH (claude CLI location)
export PATH="$HOME/.local/bin:$PATH"

# Check if virtual environment exists
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Start the server
python3 -m src.server.main
