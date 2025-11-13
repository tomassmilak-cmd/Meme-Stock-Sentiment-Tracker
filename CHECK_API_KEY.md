# How to Set Up Your Polygon API Key

## Current Status
Your Polygon API key is still set to the placeholder value: `your_polygon_api_key_here`

## Steps to Fix

### 1. Get Your Polygon API Key
1. Go to: **https://polygon.io/dashboard/api-keys**
2. Sign up for a free account (if you don't have one)
3. Create a new API key
4. Copy the API key (it will look like: `abc123xyz789`)

### 2. Update Your .env File
Open the file: `/Users/tomassmilak/Meme-Stock-Sentiment-Tracker/.env`

Find this line:
```
POLYGON_API_KEY=your_polygon_api_key_here
```

Replace it with your actual key:
```
POLYGON_API_KEY=your_actual_key_here
```

**Important:** 
- Don't use quotes around the key
- Don't leave any spaces
- Make sure you replace the entire placeholder

### 3. Restart the API Server
The server should auto-reload, but if needed:
```bash
# Kill the current server
pkill -f "uvicorn api.main:app"

# Restart it
cd /Users/tomassmilak/Meme-Stock-Sentiment-Tracker
python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Test It
```bash
curl -X POST http://localhost:8000/api/track-popular
```

You should see tickers being tracked successfully!

## Free Tier Limits
Polygon.io free tier includes:
- 5 API calls per minute
- Real-time and historical stock data
- Perfect for testing and small projects


