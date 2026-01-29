#!/bin/bash
# =============================================================================
# AI Secretary System - Docker Start Script
# Starts local vLLM + Docker containers with one command
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🚀 Starting AI Secretary System${NC}"

# Check if vLLM is already running
if curl -s http://localhost:11434/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ vLLM already running${NC}"
else
    echo -e "${YELLOW}Starting vLLM...${NC}"
    # Start vLLM in background
    ./start_qwen.sh &
    VLLM_PID=$!

    # Wait for vLLM to be ready (max 120 seconds)
    echo -n "Waiting for vLLM to start"
    for i in {1..60}; do
        if curl -s http://localhost:11434/health > /dev/null 2>&1; then
            echo -e "\n${GREEN}✓ vLLM ready${NC}"
            break
        fi
        echo -n "."
        sleep 2
    done

    if ! curl -s http://localhost:11434/health > /dev/null 2>&1; then
        echo -e "\n${YELLOW}⚠ vLLM not responding, continuing anyway (will use Gemini fallback)${NC}"
    fi
fi

# Start Docker containers
echo -e "${YELLOW}Starting Docker containers...${NC}"
docker compose up -d

# Wait for orchestrator to be healthy
echo -n "Waiting for orchestrator"
for i in {1..30}; do
    if curl -s http://localhost:8002/health > /dev/null 2>&1; then
        echo -e "\n${GREEN}✓ Orchestrator ready${NC}"
        break
    fi
    echo -n "."
    sleep 2
done

echo ""
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ AI Secretary System started!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo ""
echo "  Admin Panel: http://localhost:8002/admin/"
echo "  Health:      http://localhost:8002/health"
echo ""
echo "  Logs:        docker compose logs -f orchestrator"
echo "  Stop:        ./stop_docker.sh"
echo ""
