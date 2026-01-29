#!/bin/bash
# =============================================================================
# AI Secretary System - Docker Stop Script
# Stops Docker containers and optionally vLLM
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Stopping Docker containers...${NC}"
docker compose down

# Ask about vLLM
if pgrep -f "vllm.entrypoints" > /dev/null 2>&1; then
    echo ""
    read -p "Stop vLLM as well? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Stopping vLLM...${NC}"
        pkill -f "vllm.entrypoints" 2>/dev/null || true
        echo -e "${GREEN}✓ vLLM stopped${NC}"
    else
        echo "vLLM left running (for faster restart)"
    fi
fi

echo -e "${GREEN}✓ Stopped${NC}"
