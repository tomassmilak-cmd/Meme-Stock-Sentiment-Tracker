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

# Initialize services (database uses lazy connection)
# Don't initialize database at module level to avoid blocking
db = None

def get_db():
    """Get database instance, initialize if needed."""
    global db
    if db is None:
        try:
            db = DatabaseManager()
        except Exception as e:
            print(f"Warning: Could not initialize database: {e}")
            return None
    return db

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
    global monitoring_active
    monitoring_active = False  # Stop monitoring first
    
    try:
        db_instance = get_db()
        if db_instance:
            db_instance.close()
    except Exception as e:
        print(f"Warning: Error during shutdown: {e}")


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
    db_instance = get_db()
    if not db_instance:
        return {"tickers": []}
    try:
        tickers = db_instance.get_trending_tickers(hours=hours, limit=limit)
        print(f"API: get_trending_tickers returned {len(tickers)} tickers")
        # If no social mentions, return stock prices as fallback
        if not tickers:
            print("API: No tickers from DB, trying fallback...")
            # Get any stock prices we have - use simplest query possible
            try:
                # First check if table exists and has data
                count = db_instance.conn.execute("SELECT COUNT(*) FROM stock_prices").fetchone()[0]
                print(f"Stock prices in DB: {count}")
                
                if count > 0:
                    # Try simplest possible query
                    try:
                        result = db_instance.conn.execute("SELECT ticker, price FROM stock_prices LIMIT ?", [limit]).fetchall()
                        print(f"API fallback query returned {len(result)} rows")
                    except Exception as qe:
                        print(f"Query error: {qe}")
                        result = []
                    
                    if result:
                        # Deduplicate by ticker, keeping latest
                        seen = {}
                        for row in result:
                            if row[0] not in seen:
                                seen[row[0]] = row[1]
                        
                        tickers = [
                            {
                                "ticker": ticker,
                                "latest_price": float(price) if price else None,
                                "mention_count": 0,
                                "avg_sentiment": 0.0,
                                "price_change_24h": None
                            }
                            for ticker, price in seen.items()
                        ]
                        print(f"API fallback: Returning {len(tickers)} tickers from stock_prices")
            except Exception as e:
                print(f"Error getting fallback data: {e}")
                import traceback
                traceback.print_exc()
        return {"tickers": tickers}
    except Exception as e:
        print(f"Error in get_trending_tickers: {e}")
        return {"tickers": []}


@app.get("/api/ticker/{ticker}/sentiment")
async def get_ticker_sentiment(ticker: str, hours: int = 24):
    """Get sentiment trend for a ticker."""
    db_instance = get_db()
    if not db_instance:
        return {"ticker": ticker.upper(), "trend": []}
    trend = db_instance.get_ticker_sentiment_trend(ticker.upper(), hours=hours)
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
    db_instance = get_db()
    if not db_instance:
        return {"ticker": ticker.upper(), "history": []}
    history = db_instance.get_ticker_price_history(ticker.upper(), days=days)
    return {"ticker": ticker.upper(), "history": history}


@app.get("/api/ticker/{ticker}/stats")
async def get_ticker_stats(ticker: str, hours: int = 24):
    """Get comprehensive stats for a ticker."""
    db_instance = get_db()
    if not db_instance:
        return {
            "ticker": ticker.upper(),
            "sentiment_trend": [],
            "current_price": None,
            "price_change": None,
            "mention_count": 0,
            "avg_sentiment": 0.0
        }
    
    # Get sentiment trend
    sentiment_trend = db_instance.get_ticker_sentiment_trend(ticker.upper(), hours=hours)
    
    # Get current price
    current_price = price_service.get_current_price(ticker.upper())
    
    # Get price change
    price_change = price_service.get_price_change(ticker.upper(), hours=hours)
    
    # Get mention count
    trending = db_instance.get_trending_tickers(hours=hours, limit=1000)
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
    db_instance = get_db()
    if not db_instance:
        return {"anomalies": []}
    
    trending = db_instance.get_trending_tickers(hours=hours, limit=100)
    
    # Calculate current mention counts
    ticker_counts = {t['ticker']: t['mention_count'] for t in trending}
    
    # Detect anomalies
    anomalies = anomaly_detector.detect_anomalies(ticker_counts)
    
    return {"anomalies": list(anomalies.values())}


@app.post("/api/ticker/{ticker}/track")
async def track_ticker(ticker: str):
    """Manually add a ticker to track (Polygon only mode)."""
    ticker = ticker.upper()
    db_instance = get_db()
    if not db_instance:
        return {"error": "Database not initialized"}
    
    try:
        # Fetch current price
        price_data = price_service.get_current_price(ticker)
        if price_data:
            db_instance.insert_stock_price(price_data)
            
            # Fetch historical prices
            try:
                historical = price_service.get_historical_prices(ticker, days=7)
                if historical:
                    db_instance.insert_historical_prices(historical)
            except Exception as e:
                print(f"Warning: Could not fetch historical prices for {ticker}: {e}")
            
            return {
                "message": f"Ticker {ticker} is now being tracked",
                "price": price_data
            }
        else:
            return {"error": f"Could not fetch price for {ticker}. Check if ticker is valid."}
    except Exception as e:
        import traceback
        print(f"Error in track_ticker: {e}")
        traceback.print_exc()
        return {"error": f"Error tracking {ticker}: {str(e)}"}


@app.get("/api/popular-tickers")
async def get_popular_tickers():
    """Get list of popular meme stock tickers to track."""
    # Common meme stocks
    popular_tickers = [
        "GME", "AMC", "BB", "NOK", "PLTR", "TSLA", "AAPL", "MSFT",
        "NVDA", "AMD", "SPY", "QQQ", "RIVN", "LCID", "SOFI", "HOOD"
    ]
    return {"tickers": popular_tickers}


@app.get("/api/status")
async def get_api_status():
    """Check API configuration status."""
    status = {
        "polygon_configured": price_service.client is not None,
        "polygon_api_key_set": settings.polygon_api_key is not None and settings.polygon_api_key != "your_polygon_api_key_here",
        "reddit_configured": reddit_monitor.subreddit is not None,
        "twitter_configured": twitter_monitor.client is not None,
    }
    
    # Test Polygon API if configured
    if status["polygon_configured"]:
        try:
            test_price = price_service.get_current_price("AAPL")
            status["polygon_working"] = test_price is not None
            if not status["polygon_working"]:
                status["polygon_error"] = "API key may be invalid - check your .env file"
        except Exception as e:
            status["polygon_working"] = False
            status["polygon_error"] = str(e)
    else:
        status["polygon_working"] = False
        status["polygon_error"] = "Massive.com API key not configured. Add POLYGON_API_KEY to .env file"
    
    return status


async def track_tickers_background(tickers: List[str]):
    """Background task to track multiple tickers."""
    db_instance = get_db()
    if not db_instance:
        return
    
    tracked = []
    for ticker in tickers:
        try:
            price_data = price_service.get_current_price(ticker)
            if price_data:
                db_instance.insert_stock_price(price_data)
                try:
                    historical = price_service.get_historical_prices(ticker, days=7)
                    if historical:
                        db_instance.insert_historical_prices(historical)
                except Exception as e:
                    print(f"Warning: Could not fetch historical for {ticker}: {e}")
                tracked.append(ticker)
        except Exception as e:
            print(f"Error tracking {ticker}: {e}")
    
    print(f"Background tracking complete: {len(tracked)} tickers tracked")


@app.post("/api/track-popular")
async def track_popular_tickers(background_tasks: BackgroundTasks):
    """Track popular meme stock tickers using Polygon only."""
    # Check if Polygon API key is configured
    if not price_service.client:
        return {
            "error": "Polygon API key not configured",
            "message": "Please add your POLYGON_API_KEY to the .env file. Get your key from https://massive.com/dashboard/api-keys"
        }
    
    db_instance = get_db()
    if not db_instance:
        return {
            "error": "Database not initialized",
            "message": "Database connection failed"
        }
    
    popular_tickers = [
        "GME", "AMC", "BB", "NOK", "PLTR", "TSLA", "AAPL", "MSFT",
        "NVDA", "AMD", "SPY", "QQQ", "RIVN", "LCID", "SOFI", "HOOD"
    ]
    
    # Quickly fetch first 5 tickers synchronously so dashboard shows data immediately
    quick_tracked = []
    for ticker in popular_tickers[:5]:
        try:
            price_data = price_service.get_current_price(ticker)
            if price_data:
                db_instance.insert_stock_price(price_data)
                quick_tracked.append(ticker)
        except Exception as e:
            print(f"Quick track error for {ticker}: {e}")
    
    # Start tracking remaining tickers in background
    if len(popular_tickers) > 5:
        background_tasks.add_task(track_tickers_background, popular_tickers[5:])
    
    return {
        "message": f"Tracking {len(popular_tickers)} popular tickers ({len(quick_tracked)} ready now)",
        "tracked": popular_tickers,
        "quick_tracked": quick_tracked,
        "status": "processing"
    }


@app.post("/api/monitor/start")
async def start_monitoring(background_tasks: BackgroundTasks):
    """Start monitoring Reddit and Twitter."""
    global monitoring_active
    
    if monitoring_active:
        return {"message": "Monitoring already active", "status": "active"}
    
    monitoring_active = True
    # Start background task without blocking
    try:
        background_tasks.add_task(monitor_social_media)
    except Exception as e:
        print(f"Error starting background task: {e}")
        monitoring_active = False
        return {"error": str(e), "status": "error"}
    
    return {"message": "Monitoring started", "status": "started"}


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
    """Background task to monitor social media and/or stock prices."""
    global monitoring_active
    
    db_instance = get_db()
    if not db_instance:
        print("Error: Database not initialized, cannot monitor")
        monitoring_active = False
        return
    
    print("Starting monitoring with Twitter and Polygon...")
    
    # Popular meme stocks to track
    popular_tickers = [
        "GME", "AMC", "BB", "NOK", "PLTR", "TSLA", "AAPL", "MSFT",
        "NVDA", "AMD", "SPY", "QQQ", "RIVN", "LCID", "SOFI", "HOOD"
    ]
    
    # Track all mentioned tickers
    all_tickers = set(popular_tickers)  # Start with popular tickers
    
    iteration = 0
    while monitoring_active:
        try:
            iteration += 1
            print(f"Monitoring iteration {iteration} - Tracking {len(all_tickers)} tickers")
            
            # Monitor Reddit posts (if configured)
            if reddit_monitor.subreddit:
                try:
                    print("Monitoring Reddit posts...")
                    post_count = 0
                    for post in reddit_monitor.stream_posts():
                        if not monitoring_active:
                            break
                        if post_count >= 10:  # Limit posts per iteration
                            break
                        
                        db_instance.insert_social_mention(post)
                        all_tickers.update(post['tickers'])
                        post_count += 1
                        
                        # Update anomaly detector
                        for ticker in post['tickers']:
                            anomaly_detector.add_mention(ticker)
                    if post_count > 0:
                        print(f"  Found {post_count} Reddit posts with tickers")
                except Exception as e:
                    print(f"Error in Reddit monitoring: {e}")
            
            # Monitor Reddit comments (if configured)
            if reddit_monitor.subreddit:
                try:
                    print("Monitoring Reddit comments...")
                    comment_count = 0
                    for comment in reddit_monitor.stream_comments():
                        if not monitoring_active:
                            break
                        if comment_count >= 10:  # Limit comments per iteration
                            break
                        
                        db_instance.insert_social_mention(comment)
                        all_tickers.update(comment['tickers'])
                        comment_count += 1
                        
                        for ticker in comment['tickers']:
                            anomaly_detector.add_mention(ticker)
                    if comment_count > 0:
                        print(f"  Found {comment_count} Reddit comments with tickers")
                except Exception as e:
                    print(f"Error in Reddit comment monitoring: {e}")
            
            # Monitor Twitter (if configured) - Active search
            if twitter_monitor.client:
                try:
                    print("Monitoring Twitter...")
                    # Search for popular tickers on Twitter
                    tickers_to_search = list(all_tickers)[:10] if len(all_tickers) > 10 else list(all_tickers)
                    tweets = twitter_monitor.search_stock_tickers(
                        tickers_to_search,
                        max_results_per_ticker=10  # Limit to avoid rate limits
                    )
                    
                    if tweets:
                        print(f"  Found {len(tweets)} tweets with tickers")
                        for tweet in tweets:
                            db_instance.insert_social_mention(tweet)
                            all_tickers.update(tweet['tickers'])
                            
                            for ticker in tweet['tickers']:
                                anomaly_detector.add_mention(ticker)
                    else:
                        print("  No tweets found this iteration")
                except Exception as e:
                    print(f"Error in Twitter monitoring: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Update stock prices periodically (Polygon mode - always run)
            if all_tickers and price_service.client:
                try:
                    prices = price_service.get_batch_prices(list(all_tickers)[:50])
                    for ticker, price_data in prices.items():
                        if price_data:
                            db_instance.insert_stock_price(price_data)
                    
                    # Also fetch historical prices for tracked tickers
                    for ticker in list(all_tickers)[:20]:  # Limit to avoid rate limits
                        try:
                            historical = price_service.get_historical_prices(ticker, days=7)
                            if historical:
                                db_instance.insert_historical_prices(historical)
                        except Exception as e:
                            print(f"Error fetching historical for {ticker}: {e}")
                except Exception as e:
                    print(f"Error updating stock prices: {e}")
            
            # Update ticker statistics
            if all_tickers:
                try:
                    # Get prices for all tracked tickers
                    for ticker in list(all_tickers)[:50]:
                        try:
                            current_price = price_service.get_current_price(ticker)
                            price_change = price_service.get_price_change(ticker, hours=24)
                            
                            # Get mention count from database (if any)
                            trending = db_instance.get_trending_tickers(hours=24, limit=1000)
                            ticker_data = next((t for t in trending if t['ticker'] == ticker), None)
                            mention_count = ticker_data['mention_count'] if ticker_data else 0
                            
                            stats = {
                                'ticker': ticker,
                                'timestamp': datetime.utcnow(),
                                'mention_count': mention_count,
                                'avg_sentiment': ticker_data.get('avg_sentiment', 0.0) if ticker_data else 0.0,
                                'price': current_price['price'] if current_price else None,
                                'price_change_24h': price_change['change'] if price_change else None,
                                'price_change_percent_24h': price_change['change_percent'] if price_change else None,
                                'z_score': 0.0,  # Can't calculate without mention history
                                'is_anomaly': False
                            }
                            
                            db_instance.insert_ticker_stats(stats)
                        except Exception as e:
                            print(f"Error updating stats for {ticker}: {e}")
                except Exception as e:
                    print(f"Error updating ticker stats: {e}")
            
            await asyncio.sleep(60)  # Update every minute for Polygon mode
            
        except Exception as e:
            print(f"Error in monitoring loop: {e}")
            await asyncio.sleep(60)  # Wait longer on error


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)

