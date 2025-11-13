"""FastAPI backend for Meme Stock Sentiment Tracker."""
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import List, Dict
import json
import asyncio
from datetime import datetime

from config import settings
from database.db_manager import DatabaseManager
from services.reddit_monitor import RedditMonitor
from services.twitter_monitor import TwitterMonitor
from services.stock_price_service import StockPriceService
from utils.anomaly_detector import AnomalyDetector

app = FastAPI(title="Meme Stock Sentiment Tracker API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
db = DatabaseManager()
reddit_monitor = RedditMonitor()
twitter_monitor = TwitterMonitor()
price_service = StockPriceService()
anomaly_detector = AnomalyDetector(z_threshold=settings.z_score_threshold)

# Background task state
monitoring_active = False


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    print("Starting Meme Stock Sentiment Tracker API...")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    db.close()


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Meme Stock Sentiment Tracker API",
        "version": "1.0.0"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/trending")
async def get_trending_tickers(hours: int = 24, limit: int = 20):
    """Get trending tickers."""
    tickers = db.get_trending_tickers(hours=hours, limit=limit)
    return {"tickers": tickers}


@app.get("/api/ticker/{ticker}/sentiment")
async def get_ticker_sentiment(ticker: str, hours: int = 24):
    """Get sentiment trend for a ticker."""
    trend = db.get_ticker_sentiment_trend(ticker.upper(), hours=hours)
    return {"ticker": ticker.upper(), "trend": trend}


@app.get("/api/ticker/{ticker}/price")
async def get_ticker_price(ticker: str):
    """Get current price for a ticker."""
    price = price_service.get_current_price(ticker.upper())
    if not price:
        return {"error": "Price not found"}
    return price


@app.get("/api/ticker/{ticker}/price-history")
async def get_ticker_price_history(ticker: str, days: int = 7):
    """Get price history for a ticker."""
    history = db.get_ticker_price_history(ticker.upper(), days=days)
    return {"ticker": ticker.upper(), "history": history}


@app.get("/api/ticker/{ticker}/stats")
async def get_ticker_stats(ticker: str, hours: int = 24):
    """Get comprehensive stats for a ticker."""
    # Get sentiment trend
    sentiment_trend = db.get_ticker_sentiment_trend(ticker.upper(), hours=hours)
    
    # Get current price
    current_price = price_service.get_current_price(ticker.upper())
    
    # Get price change
    price_change = price_service.get_price_change(ticker.upper(), hours=hours)
    
    # Get mention count
    trending = db.get_trending_tickers(hours=hours, limit=1000)
    ticker_data = next((t for t in trending if t['ticker'] == ticker.upper()), None)
    
    return {
        "ticker": ticker.upper(),
        "sentiment_trend": sentiment_trend,
        "current_price": current_price,
        "price_change": price_change,
        "mention_count": ticker_data['mention_count'] if ticker_data else 0,
        "avg_sentiment": ticker_data['avg_sentiment'] if ticker_data else 0.0
    }


@app.get("/api/anomalies")
async def get_anomalies(hours: int = 24):
    """Get detected anomalies."""
    trending = db.get_trending_tickers(hours=hours, limit=100)
    
    # Calculate current mention counts
    ticker_counts = {t['ticker']: t['mention_count'] for t in trending}
    
    # Detect anomalies
    anomalies = anomaly_detector.detect_anomalies(ticker_counts)
    
    return {"anomalies": list(anomalies.values())}


@app.post("/api/monitor/start")
async def start_monitoring(background_tasks: BackgroundTasks):
    """Start monitoring Reddit and Twitter."""
    global monitoring_active
    
    if monitoring_active:
        return {"message": "Monitoring already active"}
    
    monitoring_active = True
    background_tasks.add_task(monitor_social_media)
    
    return {"message": "Monitoring started"}


@app.post("/api/monitor/stop")
async def stop_monitoring():
    """Stop monitoring."""
    global monitoring_active
    monitoring_active = False
    return {"message": "Monitoring stopped"}


@app.get("/api/stream/mentions")
async def stream_mentions():
    """Stream social media mentions in real-time."""
    async def generate():
        while monitoring_active:
            # Get recent mentions from database
            # This is a simplified version - in production, use proper streaming
            yield f"data: {json.dumps({'type': 'ping', 'timestamp': datetime.utcnow().isoformat()})}\n\n"
            await asyncio.sleep(5)
    
    return StreamingResponse(generate(), media_type="text/event-stream")


async def monitor_social_media():
    """Background task to monitor social media."""
    global monitoring_active
    
    print("Starting social media monitoring...")
    
    # Track all mentioned tickers
    all_tickers = set()
    
    while monitoring_active:
        try:
            # Monitor Reddit posts
            try:
                for post in reddit_monitor.stream_posts():
                    if not monitoring_active:
                        break
                    
                    db.insert_social_mention(post)
                    all_tickers.update(post['tickers'])
                    
                    # Update anomaly detector
                    for ticker in post['tickers']:
                        anomaly_detector.add_mention(ticker)
            except Exception as e:
                print(f"Error in Reddit monitoring: {e}")
            
            # Monitor Reddit comments
            try:
                for comment in reddit_monitor.stream_comments():
                    if not monitoring_active:
                        break
                    
                    db.insert_social_mention(comment)
                    all_tickers.update(comment['tickers'])
                    
                    for ticker in comment['tickers']:
                        anomaly_detector.add_mention(ticker)
            except Exception as e:
                print(f"Error in Reddit comment monitoring: {e}")
            
            # Monitor Twitter (periodic search)
            if all_tickers:
                try:
                    tweets = twitter_monitor.search_stock_tickers(
                        list(all_tickers)[:10],  # Limit to top 10 tickers
                        max_results_per_ticker=20
                    )
                    
                    for tweet in tweets:
                        db.insert_social_mention(tweet)
                        all_tickers.update(tweet['tickers'])
                        
                        for ticker in tweet['tickers']:
                            anomaly_detector.add_mention(ticker)
                except Exception as e:
                    print(f"Error in Twitter monitoring: {e}")
            
            # Update stock prices periodically
            if all_tickers:
                try:
                    prices = price_service.get_batch_prices(list(all_tickers)[:50])
                    for ticker, price_data in prices.items():
                        db.insert_stock_price(price_data)
                except Exception as e:
                    print(f"Error updating stock prices: {e}")
            
            # Update ticker statistics
            if all_tickers:
                try:
                    trending = db.get_trending_tickers(hours=1, limit=100)
                    ticker_counts = {t['ticker']: t['mention_count'] for t in trending}
                    
                    for ticker_data in trending:
                        ticker = ticker_data['ticker']
                        count = ticker_data['mention_count']
                        
                        z_score = anomaly_detector.calculate_z_score(ticker, count)
                        is_anomaly = abs(z_score) >= settings.z_score_threshold
                        
                        price_change = price_service.get_price_change(ticker, hours=24)
                        
                        stats = {
                            'ticker': ticker,
                            'mention_count': count,
                            'avg_sentiment': ticker_data.get('avg_sentiment', 0.0),
                            'price': ticker_data.get('latest_price'),
                            'price_change_24h': price_change['change'] if price_change else None,
                            'price_change_percent_24h': price_change['change_percent'] if price_change else None,
                            'z_score': z_score,
                            'is_anomaly': is_anomaly
                        }
                        
                        db.insert_ticker_stats(stats)
                except Exception as e:
                    print(f"Error updating ticker stats: {e}")
            
            await asyncio.sleep(10)  # Small delay between iterations
            
        except Exception as e:
            print(f"Error in monitoring loop: {e}")
            await asyncio.sleep(60)  # Wait longer on error


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)

