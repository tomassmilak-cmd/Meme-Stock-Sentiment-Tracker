#!/bin/bash

# Setup script for Meme Stock Sentiment Tracker

echo "🚀 Setting up Meme Stock Sentiment Tracker..."

# Create data directory
mkdir -p data
mkdir -p logs

# Check if .env exists
if [ ! -f .env ]; then
    echo "📝 Creating .env file from .env.example..."
    cp .env.example .env
    echo "⚠️  Please edit .env and add your API credentials!"
else
    echo "✅ .env file already exists"
fi

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "🐍 Python version: $python_version"

# Install dependencies
echo "📦 Installing Python dependencies..."
pip3 install -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env and add your API credentials"
echo "2. Start the API: uvicorn api.main:app --reload"
echo "3. Start the dashboard: streamlit run dashboard/app.py"
echo "4. Or use Docker: docker-compose up"
echo ""

