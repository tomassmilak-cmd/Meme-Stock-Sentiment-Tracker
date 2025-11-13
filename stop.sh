#!/bin/bash

# Stop script for Meme Stock Sentiment Tracker

echo "🛑 Stopping Meme Stock Sentiment Tracker..."

# Stop API server
pkill -f "uvicorn api.main:app"
echo "✓ API server stopped"

# Stop Dashboard
pkill -f "streamlit run dashboard"
echo "✓ Dashboard stopped"

echo ""
echo "✅ All services stopped"

