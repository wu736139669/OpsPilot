#!/bin/bash
# OpsPilot Startup Script
# Usage: ./start.sh [port]

PORT=${1:-${OPSPILOT_PORT:-5016}}

echo "============================================"
echo "  OpsPilot - AI Coding Agent Control Center"
echo "============================================"
echo ""
echo "  Starting on port $PORT ..."
echo "  Dashboard: http://localhost:$PORT"
echo ""
echo "  Requirements:"
echo "    - Python 3.9+"
echo "    - tmux"
echo "    - Claude Code CLI (optional, for agents)"
echo ""

# Check Python
python3 --version > /dev/null 2>&1 || { echo "❌ Python 3 required"; exit 1; }

# Check tmux
tmux -V > /dev/null 2>&1 || { echo "⚠️  tmux not found (required for agent control)"; }

# Install dependencies if needed
pip3 install -q fastapi uvicorn websockets 2>/dev/null

# Ensure directories
mkdir -p state logs

# Start server
export OPSPILOT_PORT=$PORT
python3 server.py
