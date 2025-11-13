#!/bin/bash
# Script to safely restart the API server

echo "🛑 Stopping existing API server..."

# Kill any existing uvicorn processes
pkill -f "uvicorn api.main:app" 2>/dev/null
sleep 2

# Check if port is still in use
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "⚠️  Port 8000 still in use, force killing..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null
    sleep 2
fi

echo "🚀 Starting API server..."

cd "$(dirname "$0")"
python3 -m uvicorn api.main:app --host 127.0.0.1 --port 8000 > /tmp/api.log 2>&1 &

# Wait a moment for server to start
sleep 3

# Check if server started successfully
if curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; then
    echo "✅ API server started successfully!"
    echo "   Health check: http://127.0.0.1:8000/health"
    echo "   API docs: http://127.0.0.1:8000/docs"
    echo "   Logs: tail -f /tmp/api.log"
else
    echo "❌ API server failed to start. Check logs:"
    echo "   tail -f /tmp/api.log"
    exit 1
fi

