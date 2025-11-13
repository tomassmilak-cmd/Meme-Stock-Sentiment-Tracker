# Quick Start Guide

## Services Status
Both services should be running. To verify:
- API: http://localhost:8000/health
- Dashboard: http://localhost:8501

## Start Data Collection

Open a terminal and run these commands:

```bash
# 1. Start monitoring (collects Twitter + Polygon data)
curl -X POST http://localhost:8000/api/monitor/start

# 2. Track popular stocks (gets initial price data)
curl -X POST http://localhost:8000/api/track-popular

# 3. Check trending tickers
curl http://localhost:8000/api/trending
```

## Access Points

- **Dashboard**: http://localhost:8501
- **API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

## What's Running

✅ **Twitter API**: Collecting tweets mentioning stock tickers
✅ **Polygon/Massive API**: Fetching stock prices
✅ **Dashboard**: Displaying data in real-time

## View Data

1. Open http://localhost:8501 in your browser
2. Wait 1-2 minutes for data to appear
3. Check the "Leaderboard" tab to see trending tickers

## Troubleshooting

If you don't see data:
1. Make sure monitoring is started: `curl -X POST http://localhost:8000/api/monitor/start`
2. Check API status: `curl http://localhost:8000/api/status`
3. Wait a few minutes for data to accumulate

