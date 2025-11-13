#!/bin/bash
# Simple script to start data collection

echo "Starting data collection..."

# Start monitoring
echo "Starting monitoring..."
curl -X POST http://localhost:8000/api/monitor/start

echo ""
echo "Tracking popular stocks..."
curl -X POST http://localhost:8000/api/track-popular

echo ""
echo "Done! Check http://localhost:8501 to see the data"

