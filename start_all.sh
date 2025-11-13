#!/bin/bash
# Script to start both API server and dashboard

echo "🚀 Starting Meme Stock Sentiment Tracker..."

# Kill any existing processes
echo "🛑 Stopping existing services..."
pkill -f "uvicorn api.main:app" 2>/dev/null
pkill -f "streamlit run dashboard" 2>/dev/null
pkill -f "python3 -m streamlit" 2>/dev/null
sleep 3

# Clear port if needed
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "⚠️  Port 8000 in use, clearing..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null
    sleep 2
fi

if lsof -Pi :8501 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "⚠️  Port 8501 in use, clearing..."
    lsof -ti:8501 | xargs kill -9 2>/dev/null
    sleep 2
fi

cd "$(dirname "$0")"

# Start API server
echo "📡 Starting API server..."

# Check if already running
if curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; then
    echo "✅ API server already running"
    API_PID=$(ps aux | grep "uvicorn api.main:app" | grep -v grep | awk '{print $2}' | head -1)
    echo "   PID: $API_PID"
else
    python3 -m uvicorn api.main:app --host 127.0.0.1 --port 8000 > /tmp/api.log 2>&1 &
    API_PID=$!
    sleep 4
    
    # Check API
    if curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; then
        echo "✅ API server started (PID: $API_PID)"
    else
        echo "❌ API server failed to start. Check /tmp/api.log"
        echo "   Last 10 lines of log:"
        tail -10 /tmp/api.log
        exit 1
    fi
fi

# Start Dashboard
echo "📊 Starting dashboard..."

# Check if already running
if curl -s http://localhost:8501 > /dev/null 2>&1; then
    echo "✅ Dashboard already running"
    DASH_PID=$(ps aux | grep "streamlit run dashboard" | grep -v grep | awk '{print $2}' | head -1)
    echo "   PID: $DASH_PID"
else
    python3 -m streamlit run dashboard/app.py --server.port 8501 --server.address 0.0.0.0 --server.headless=true > /tmp/dashboard.log 2>&1 &
    DASH_PID=$!
    sleep 6
    
    # Check Dashboard
    if curl -s http://localhost:8501 > /dev/null 2>&1; then
        echo "✅ Dashboard started (PID: $DASH_PID)"
    else
        echo "⚠️  Dashboard may still be starting. Check /tmp/dashboard.log"
        echo "   Last 5 lines of log:"
        tail -5 /tmp/dashboard.log
    fi
fi

echo ""
echo "🎉 Services started!"
echo "   API: http://127.0.0.1:8000"
echo "   API Docs: http://127.0.0.1:8000/docs"
echo "   Dashboard: http://localhost:8501"
echo ""
echo "To stop services: ./stop_all.sh"
echo "To view logs: tail -f /tmp/api.log or tail -f /tmp/dashboard.log"

