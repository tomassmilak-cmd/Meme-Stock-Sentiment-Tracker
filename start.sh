#!/bin/bash

# Startup script for Meme Stock Sentiment Tracker
# This script starts the API server, dashboard, and begins data collection

echo "🚀 Starting Meme Stock Sentiment Tracker..."
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if API server is running
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} API server is already running"
else
    echo -e "${YELLOW}→${NC} Starting API server..."
    cd "$(dirname "$0")"
    python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload > /tmp/meme_stock_api.log 2>&1 &
    API_PID=$!
    echo "  API server started (PID: $API_PID)"
    sleep 5
fi

# Check if Dashboard is running
if curl -s http://localhost:8501 > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Dashboard is already running"
else
    echo -e "${YELLOW}→${NC} Starting Dashboard..."
    cd "$(dirname "$0")"
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false python3 -m streamlit run dashboard/app.py --server.port 8501 --server.address 0.0.0.0 --server.headless=true > /tmp/meme_stock_dashboard.log 2>&1 &
    DASHBOARD_PID=$!
    echo "  Dashboard started (PID: $DASHBOARD_PID)"
    sleep 5
fi

# Wait for API to be ready
echo ""
echo "⏳ Waiting for services to be ready..."
sleep 5

# Start monitoring and tracking in background
echo ""
echo -e "${YELLOW}→${NC} Starting data collection (this may take a moment)..."
(sleep 3 && curl -s -X POST http://localhost:8000/api/monitor/start > /dev/null 2>&1 && echo "Monitoring started") &
(sleep 5 && curl -s -X POST http://localhost:8000/api/track-popular > /dev/null 2>&1 && echo "Stock tracking started") &

# Final status
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}✅ Meme Stock Sentiment Tracker is running!${NC}"
echo ""
echo "📍 Access Points:"
echo "   Dashboard: http://localhost:8501"
echo "   API:       http://localhost:8000"
echo "   API Docs:  http://localhost:8000/docs"
echo ""
echo "📝 Logs:"
echo "   API:      /tmp/meme_stock_api.log"
echo "   Dashboard: /tmp/meme_stock_dashboard.log"
echo ""
echo "💡 Data collection is now active!"
echo "   - Twitter mentions are being collected"
echo "   - Stock prices are being tracked"
echo "   - Check the dashboard in a few minutes to see data"
echo ""
echo "Press Ctrl+C to stop (or run ./stop.sh)"

