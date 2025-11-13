#!/bin/bash
# Script to stop both API server and dashboard

echo "🛑 Stopping services..."

pkill -f "uvicorn api.main:app" 2>/dev/null
pkill -f "streamlit run dashboard" 2>/dev/null
pkill -f "python3 -m streamlit" 2>/dev/null

# Force kill if needed
sleep 2
lsof -ti:8000 | xargs kill -9 2>/dev/null
lsof -ti:8501 | xargs kill -9 2>/dev/null

echo "✅ Services stopped"

