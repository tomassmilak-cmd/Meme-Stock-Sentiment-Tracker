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
from utils.sentiment_analyzer import SentimentAnalyzer

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
    return {"message": "Meme Stock Sentiment Tracker API", "version": "1.0.0"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/trending")
async def get_trending_tickers(hours: int = 24, limit: int = 5000):
    """Get trending tickers - optimized for speed."""
    db_instance = get_db()
    if not db_instance:
        return {"tickers": []}

    try:
        # Cap limit to prevent timeouts - max 5000 (increased from 2000)
        limit = min(limit, 5000)

        # Get tickers from database - this should be fast now
        tickers = db_instance.get_trending_tickers(hours=hours, limit=limit)
        print(f"API: Returning {len(tickers)} trending tickers")

        # Ensure all tickers have required fields
        for ticker in tickers:
            if "twitter_mentions" not in ticker:
                ticker["twitter_mentions"] = 0
            if "polygon_mentions" not in ticker:
                ticker["polygon_mentions"] = 0

        return {"tickers": tickers}
    except Exception as e:
        print(f"Error in get_trending_tickers: {e}")
        import traceback

        traceback.print_exc()
        # Always return something, even if empty
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
    ticker_upper = ticker.upper()
    db_instance = get_db()
    
    # First try to get from database (cached price)
    if db_instance:
        try:
            latest_price = db_instance.conn.execute(
                """
                SELECT price FROM stock_prices
                WHERE ticker = ?
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (ticker_upper,),
            ).fetchone()
            
            if latest_price:
                return {
                    "ticker": ticker_upper,
                    "price": float(latest_price[0]),
                    "timestamp": datetime.utcnow(),
                    "source": "database"
                }
        except Exception as e:
            pass  # Continue to try Yahoo Finance
    
    # If not in database, try Yahoo Finance
    price = price_service.get_current_price(ticker_upper)
    if price:
        # Store in database for future use
        if db_instance:
            try:
                db_instance.insert_stock_price(price)
            except:
                pass
        return price
    
    # If both fail, return error
    return {"error": "Price not found - Yahoo Finance may be rate limited"}


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
    ticker_upper = ticker.upper()

    if not db_instance:
        return {
            "ticker": ticker_upper,
            "sentiment_trend": [],
            "current_price": None,
            "price_change": None,
            "mention_count": 0,
            "twitter_mentions": 0,
            "polygon_mentions": 0,
            "avg_sentiment": 0.0,
            "latest_price": None,
            "price_change_24h": None,
            "price_change_percent_24h": None,
        }

    # Get comprehensive stats from database (includes mentions, sentiment,
    # prices)
    db_stats = db_instance.get_ticker_stats(ticker_upper, hours=hours)

    # Get sentiment trend with Twitter and Polygon breakdown
    sentiment_trend = db_instance.get_ticker_sentiment_trend(ticker_upper, hours=hours)

    # Get current price from API (fallback if not in database, or to get
    # real-time data)
    # Only fetch if not in database to avoid rate limiting
    current_price = None
    if not db_stats.get("latest_price"):
        try:
            current_price = price_service.get_current_price(ticker_upper)
        except Exception as e:
            pass  # Price fetch failed, use database price

    # Get price change from API (fallback if not in database)
    price_change = None
    if not db_stats.get("price_change_24h"):
        try:
            price_change = price_service.get_price_change(ticker_upper, hours=hours)
        except Exception as e:
            pass  # Price change fetch failed

    # Combine database stats with API data
    # Use database price if available, otherwise use API price
    final_price = db_stats.get("latest_price")
    if final_price is None and current_price:
        final_price = current_price.get("price")

    # Use database price change if available, otherwise use API price change
    final_price_change = db_stats.get("price_change_24h")
    final_price_change_percent = db_stats.get("price_change_percent_24h")

    if final_price_change is None and price_change:
        final_price_change = price_change.get("change")
    if final_price_change_percent is None and price_change:
        final_price_change_percent = price_change.get("change_percent")

    return {
        "ticker": ticker_upper,
        "sentiment_trend": sentiment_trend,
        "current_price": current_price if current_price else {"price": final_price},
        "price_change": (
            price_change
            if price_change
            else {"change": final_price_change, "change_percent": final_price_change_percent}
        ),
        "mention_count": db_stats.get("mention_count", 0),
        "twitter_mentions": db_stats.get("twitter_mentions", 0),
        "polygon_mentions": db_stats.get("polygon_mentions", 0),
        "avg_sentiment": db_stats.get("avg_sentiment", 0.0),
        "latest_price": final_price,
        "price_change_24h": final_price_change,
        "price_change_percent_24h": final_price_change_percent,
    }


@app.get("/api/anomalies")
async def get_anomalies(hours: int = 24):
    """Get detected anomalies."""
    db_instance = get_db()
    if not db_instance:
        return {"anomalies": []}

    trending = db_instance.get_trending_tickers(hours=hours, limit=100)

    # Calculate current mention counts
    ticker_counts = {t["ticker"]: t["mention_count"] for t in trending}

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

            return {"message": f"Ticker {ticker} is now being tracked", "price": price_data}
        else:
            return {"error": f"Could not fetch price for {ticker}. Check if ticker is valid."}
    except Exception as e:
        import traceback

        print(f"Error in track_ticker: {e}")
        traceback.print_exc()
        return {"error": f"Error tracking {ticker}: {str(e)}"}


@app.get("/api/popular-tickers")
async def get_popular_tickers():
    """Get list of popular stock tickers to track."""
    from utils.stock_list import get_cached_tickers

    tickers = get_cached_tickers()
    return {"tickers": tickers, "count": len(tickers)}


@app.get("/api/status")
async def get_api_status():
    """Check API configuration status."""
    status = {
        "yahoo_finance_configured": price_service.client is not None,
        "reddit_configured": reddit_monitor.subreddit is not None,
        "twitter_configured": False,  # Disabled - using only Yahoo Finance
    }

    # Test Yahoo Finance if configured
    if status["yahoo_finance_configured"]:
        try:
            test_price = price_service.get_current_price("AAPL")
            status["yahoo_finance_working"] = test_price is not None
            if not status["yahoo_finance_working"]:
                status["yahoo_finance_error"] = "Yahoo Finance may be rate limited - will retry"
        except Exception as e:
            status["yahoo_finance_working"] = False
            status["yahoo_finance_error"] = str(e)
    else:
        status["yahoo_finance_working"] = False
        status["yahoo_finance_error"] = "Yahoo Finance not configured"

    return status


async def quick_fetch_prices(tickers: List[str]):
    """Quickly fetch prices for initial tickers - prioritize popular stocks."""
    db_instance = get_db()
    if not db_instance:
        return

    # Prioritize known popular stocks that are likely to exist
    popular_first = [
        "AAPL",
        "MSFT",
        "GOOGL",
        "AMZN",
        "NVDA",
        "META",
        "TSLA",
        "BRK.B",
        "V",
        "XOM",
        "JNJ",
        "WMT",
        "JPM",
        "MA",
        "PG",
        "CVX",
        "LLY",
        "HD",
        "MRK",
        "ABBV",
        "AVGO",
        "COST",
        "PEP",
        "ADBE",
        "TMO",
        "MCD",
        "NFLX",
        "CSCO",
        "ABT",
        "AMD",
        "CRM",
        "CMCSA",
        "WFC",
        "ACN",
        "INTC",
        "VZ",
        "NKE",
        "PM",
        "TXN",
        "HON",
        "QCOM",
        "NEE",
        "AMGN",
        "IBM",
        "RTX",
        "T",
        "UNH",
        "LOW",
        "DIS",
        "AMAT",
        "GME",
        "AMC",
        "BB",
        "NOK",
        "PLTR",
        "SPY",
        "QQQ",
        "RIVN",
        "LCID",
        "SOFI",
    ]

    # Reorder: popular first, then rest
    ordered_tickers = []
    for ticker in popular_first:
        if ticker in tickers:
            ordered_tickers.append(ticker)
    for ticker in tickers:
        if ticker not in ordered_tickers:
            ordered_tickers.append(ticker)

    successful = 0
    failed = 0
    total_tickers = len(ordered_tickers)
    print(f"Quick fetch: Starting to fetch prices for {total_tickers} tickers...")

    # Fetch prices for ALL stocks, not just 200
    for i, ticker in enumerate(ordered_tickers):
        try:
            # Adaptive delays to avoid rate limits while processing all stocks
            if i > 0 and i % 100 == 0:
                await asyncio.sleep(3.0)  # Longer delay every 100 tickers
                print(f"Quick fetch: {i}/{total_tickers} processed, {successful} successful, {failed} failed...")
            elif i > 0 and i % 50 == 0:
                await asyncio.sleep(2.0)  # Medium delay every 50 tickers
            elif i > 0 and i % 25 == 0:
                await asyncio.sleep(1.0)  # Short delay every 25 tickers
            elif i > 0:
                await asyncio.sleep(0.5)  # Small delay between tickers

            price_data = price_service.get_current_price(ticker)
            if price_data and price_data.get("price"):
                db_instance.insert_stock_price(price_data)
                successful += 1
                if successful % 50 == 0:
                    print(f"Quick fetch: {successful} stocks with prices collected...")
            else:
                failed += 1
        except Exception as e:
            failed += 1
            if "rate limit" in str(e).lower() or "429" in str(e):
                print(f"Rate limit hit at {i}/{total_tickers}, waiting 10 seconds...")
                await asyncio.sleep(10.0)  # Wait longer on rate limit
            elif failed % 100 == 0:
                print(f"Quick fetch: {failed} failures...")

    print(f"Quick fetch complete: {successful} tickers with prices, {failed} failed out of {total_tickers} total")


async def track_tickers_background(tickers: List[str]):
    """Background task to track multiple tickers with prices, historical data, and news."""
    db_instance = get_db()
    if not db_instance:
        return

    tracked = []
    news_count = 0

    for ticker in tickers:
        try:
            # Get current price
            price_data = price_service.get_current_price(ticker)
            if price_data:
                db_instance.insert_stock_price(price_data)
                tracked.append(ticker)

            # Get historical prices (for 24h change calculation)
            try:
                historical = price_service.get_historical_prices(ticker, days=7)
                if historical:
                    db_instance.insert_historical_prices(historical)
                    print(f"  {ticker}: Added {len(historical)} days of historical data")
            except Exception as e:
                print(f"  {ticker}: Historical data error: {e}")

            # Get news articles and analyze sentiment
            try:
                news_articles = price_service.get_ticker_news(ticker, limit=10)  # Increased from 5 to 10
                if news_articles:
                    from utils.sentiment_analyzer import SentimentAnalyzer

                    sentiment_analyzer = SentimentAnalyzer()
                    for article in news_articles:
                        sentiment = sentiment_analyzer.analyze(article.get("text", ""))
                        news_mention = {
                            "id": article.get("id", f"polygon_{ticker}_{hash(article.get('title', ''))}"),
                            "source": "polygon_news",
                            "type": "news",
                            "text": article.get("text", ""),
                            "title": article.get("title", ""),
                            "url": article.get("url", ""),
                            "author_id": None,
                            "created_at": article.get("published_utc", datetime.utcnow()),
                            "retweet_count": 0,
                            "like_count": 0,
                            "reply_count": 0,
                            "quote_count": 0,
                            "tickers": [ticker],
                            "sentiment": sentiment,
                            "timestamp": datetime.utcnow(),
                        }
                        db_instance.insert_social_mention(news_mention)
                    news_count += len(news_articles)
                    if len(news_articles) > 0:
                        print(f"  {ticker}: Added {len(news_articles)} news articles with sentiment")
            except Exception as e:
                pass  # News is optional

            # Delay to avoid rate limits - adaptive delay (optimized for many
            # stocks)
            if len(tracked) > 0 and len(tracked) % 100 == 0:
                await asyncio.sleep(5.0)  # Longer delay every 100 tickers
            elif len(tracked) > 0 and len(tracked) % 50 == 0:
                await asyncio.sleep(3.0)  # Medium delay every 50 tickers
            elif len(tracked) > 0 and len(tracked) % 25 == 0:
                await asyncio.sleep(2.0)  # Short delay every 25 tickers
            else:
                # 0.8 seconds between tickers (optimized for speed)
                await asyncio.sleep(0.8)
        except Exception as e:
            print(f"Error tracking {ticker}: {e}")

    print(f"Background tracking complete: {len(tracked)} tickers tracked, {news_count} news articles added")


@app.post("/api/track-popular")
async def track_popular_tickers(background_tasks: BackgroundTasks):
    """Track thousands of stock tickers using Yahoo Finance."""
    # Yahoo Finance doesn't require an API key, so we can always proceed

    # Get comprehensive stock list (all 959 stocks)
    from utils.stock_list import get_cached_tickers

    popular_tickers = get_cached_tickers()  # Get ALL stocks (959 stocks)

    print(f"Tracking {len(popular_tickers)} stocks - fetching prices for all stocks...")

    # Fetch prices for ALL stocks in background (non-blocking)
    # Move expensive work to background
    db_instance = get_db()
    if db_instance:
        # Start quick fetch in background task for ALL stocks
        # This will fetch prices for all 959 stocks
        background_tasks.add_task(quick_fetch_prices, popular_tickers)

    # Start ALL other work in background - return immediately
    # This will fetch historical data and news for all stocks
    background_tasks.add_task(track_tickers_background, popular_tickers)

    return {
        "message": f"Tracking {len(popular_tickers)} tickers - fetching prices for all stocks in background",
        "tracked": popular_tickers[:20],  # Show first 20 in response
        "total_count": len(popular_tickers),
        "status": "processing",
        "note": "Prices are being collected for all stocks in the background. This may take several minutes.",
    }


async def fetch_historical_for_ticker(ticker: str):
    """Background task to fetch historical prices for a ticker."""
    try:
        db_instance = get_db()
        if not db_instance:
            return

        historical = price_service.get_historical_prices(ticker, days=3)
        if historical:
            db_instance.insert_historical_prices(historical)
            print(f"✅ Fetched historical prices for {ticker}")
    except Exception as e:
        print(f"Error fetching historical for {ticker}: {e}")


@app.post("/api/monitor/start")
async def start_monitoring(background_tasks: BackgroundTasks):
    """Start monitoring Polygon/Massive - collect mentions, status, and sentiment (Twitter disabled)."""
    global monitoring_active

    if monitoring_active:
        return {"message": "Monitoring already active", "status": "active"}

    monitoring_active = True

    # Start background tasks without blocking - return immediately
    try:
        # Start monitoring in background
        background_tasks.add_task(monitor_social_media)
        print("✅ Started monitor_social_media background task")

        # Also start tracking popular stocks immediately to get news data
        try:
            from utils.stock_list import get_cached_tickers

            popular_tickers = get_cached_tickers()  # Get ALL stocks (959 stocks)
            background_tasks.add_task(track_tickers_background, popular_tickers)
            print(f"✅ Started track_tickers_background for {len(popular_tickers)} stocks")
        except Exception as e:
            print(f"Warning: Could not start background tracking: {e}")
    except Exception as e:
        print(f"Error starting background task: {e}")
        import traceback

        traceback.print_exc()
        monitoring_active = False
        return {"error": str(e), "status": "error"}

    return {
        "message": "Monitoring started - collecting mentions, status, and sentiment from Yahoo Finance",
        "status": "started",
        "twitter_enabled": False,  # Disabled - using only Yahoo Finance
        "yahoo_finance_enabled": price_service.client is not None,
    }


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
            # This is a simplified version - in production, use proper
            # streaming
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

    print("Starting monitoring with Yahoo Finance (Twitter disabled)...")

    # Get comprehensive stock list (all 959 stocks)
    from utils.stock_list import get_cached_tickers

    popular_tickers = get_cached_tickers()  # Get ALL stocks (959 stocks)

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
                        all_tickers.update(post["tickers"])
                        # Update anomaly detector
                        for ticker in post.get("tickers", []):
                            anomaly_detector.add_mention(ticker)
                        post_count += 1
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
                        all_tickers.update(comment["tickers"])
                        # Update anomaly detector
                        for ticker in comment.get("tickers", []):
                            anomaly_detector.add_mention(ticker)
                        comment_count += 1
                    if comment_count > 0:
                        print(f"  Found {comment_count} Reddit comments with tickers")
                except Exception as e:
                    print(f"Error in Reddit comment monitoring: {e}")

            # Monitor Twitter (if configured) - DISABLED - Using only Polygon/Massive
            # Twitter monitoring disabled per user request - only using
            # Polygon/Massive API
            if False:  # Disabled: twitter_monitor.client
                try:
                    print("Monitoring Twitter...")
                    # Expanded popular stocks list for Twitter search
                    popular_stocks_twitter = [
                        # Tech giants
                        "AAPL",
                        "MSFT",
                        "GOOGL",
                        "GOOG",
                        "AMZN",
                        "NVDA",
                        "META",
                        "TSLA",
                        "NFLX",
                        "AMD",
                        # Finance
                        "JPM",
                        "BAC",
                        "WFC",
                        "GS",
                        "MS",
                        "C",
                        "V",
                        "MA",
                        "AXP",
                        "PYPL",
                        # Retail/Consumer
                        "WMT",
                        "TGT",
                        "COST",
                        "HD",
                        "LOW",
                        "NKE",
                        "SBUX",
                        "MCD",
                        "YUM",
                        "CMG",
                        # Healthcare
                        "JNJ",
                        "UNH",
                        "PFE",
                        "ABBV",
                        "TMO",
                        "ABT",
                        "LLY",
                        "MRK",
                        "BMY",
                        "AMGN",
                        # Energy
                        "XOM",
                        "CVX",
                        "COP",
                        "SLB",
                        "EOG",
                        "MPC",
                        "VLO",
                        "PSX",
                        "HAL",
                        "BKR",
                        # Meme stocks
                        "GME",
                        "AMC",
                        "BB",
                        "NOK",
                        "PLTR",
                        "SPCE",
                        "CLOV",
                        "WISH",
                        "SNDL",
                        "RKT",
                        # ETFs
                        "SPY",
                        "QQQ",
                        "DIA",
                        "IWM",
                        "VTI",
                        "VOO",
                        "VEA",
                        "VWO",
                        "AGG",
                        "BND",
                        # Crypto-related
                        "COIN",
                        "HOOD",
                        "SQ",
                        "MARA",
                        "RIOT",
                        "HUT",
                        "BITF",
                        # EVs
                        "RIVN",
                        "LCID",
                        "NIO",
                        "XPEV",
                        "LI",
                        "F",
                        "GM",
                        "FORD",
                        # Fintech
                        "SOFI",
                        "UPST",
                        "AFRM",
                        "LC",
                        # Other popular
                        "DIS",
                        "INTC",
                        "CRM",
                        "ORCL",
                        "ADBE",
                        "CSCO",
                        "AVGO",
                        "QCOM",
                        "TXN",
                        "HON",
                    ]

                    # Combine popular stocks with tracked tickers - search up
                    # to 200 tickers
                    tickers_to_search = list(set(popular_stocks_twitter + list(all_tickers)[:100]))[:200]
                    print(f"  Searching Twitter for {len(tickers_to_search)} tickers...")

                    # Search in batches to avoid rate limits
                    batch_size = 25  # Larger batches
                    total_tweets = 0
                    for i in range(0, len(tickers_to_search), batch_size):
                        batch = tickers_to_search[i : i + batch_size]
                        try:
                            tweets = twitter_monitor.search_stock_tickers(
                                batch, max_results_per_ticker=5  # Reduced per ticker to search more tickers
                            )

                            if tweets:
                                print(f"  Batch {i//batch_size + 1}: Found {len(tweets)} tweets")
                                for tweet in tweets:
                                    db_instance.insert_social_mention(tweet)
                                    all_tickers.update(tweet["tickers"])

                                    for ticker in tweet["tickers"]:
                                        anomaly_detector.add_mention(ticker)
                                total_tweets += len(tweets)

                            # Rate limiting between batches
                            if i + batch_size < len(tickers_to_search):
                                # Longer delay between batches
                                await asyncio.sleep(5.0)
                        except Exception as e:
                            error_msg = str(e)
                            if "rate limit" in error_msg.lower() or "429" in error_msg:
                                print(f"  Twitter rate limit - waiting longer...")
                                # Wait 60 seconds on rate limit
                                await asyncio.sleep(60)
                            else:
                                print(f"Error in Twitter batch {i//batch_size + 1}: {e}")
                            continue

                    if total_tweets > 0:
                        print(f"  ✅ Total: Found {total_tweets} tweets with tickers")
                    else:
                        print("  No tweets found this iteration (may be rate limited)")
                except Exception as e:
                    print(f"Error in Twitter monitoring: {e}")
                    import traceback

                    traceback.print_exc()

            # Monitor Yahoo Finance news and analyze sentiment
            # Check news every iteration for faster data collection
            if price_service.client:
                try:
                    print("Monitoring Yahoo Finance news...")
                    # Use existing sentiment analyzer instance from
                    # twitter_monitor
                    news_sentiment = (
                        twitter_monitor.sentiment_analyzer if twitter_monitor.client else SentimentAnalyzer()
                    )

                    # Focus on popular stocks first - expanded to 100 tickers
                    popular_stocks = [
                        # Tech giants
                        "AAPL",
                        "MSFT",
                        "GOOGL",
                        "GOOG",
                        "AMZN",
                        "NVDA",
                        "META",
                        "TSLA",
                        "NFLX",
                        "AMD",
                        # Finance
                        "JPM",
                        "BAC",
                        "WFC",
                        "GS",
                        "MS",
                        "C",
                        "V",
                        "MA",
                        "AXP",
                        "PYPL",
                        # Retail/Consumer
                        "WMT",
                        "TGT",
                        "COST",
                        "HD",
                        "LOW",
                        "NKE",
                        "SBUX",
                        "MCD",
                        "YUM",
                        "CMG",
                        # Healthcare
                        "JNJ",
                        "UNH",
                        "PFE",
                        "ABBV",
                        "TMO",
                        "ABT",
                        "LLY",
                        "MRK",
                        "BMY",
                        "AMGN",
                        # Energy
                        "XOM",
                        "CVX",
                        "COP",
                        "SLB",
                        "EOG",
                        "MPC",
                        "VLO",
                        "PSX",
                        "HAL",
                        "BKR",
                        # Meme stocks
                        "GME",
                        "AMC",
                        "BB",
                        "NOK",
                        "PLTR",
                        "SPCE",
                        "CLOV",
                        "WISH",
                        "SNDL",
                        "RKT",
                        # ETFs
                        "SPY",
                        "QQQ",
                        "DIA",
                        "IWM",
                        "VTI",
                        "VOO",
                        "VEA",
                        "VWO",
                        "AGG",
                        "BND",
                        # Crypto-related
                        "COIN",
                        "HOOD",
                        "SQ",
                        "MARA",
                        "RIOT",
                        "HUT",
                        "BITF",
                        # EVs
                        "RIVN",
                        "LCID",
                        "NIO",
                        "XPEV",
                        "LI",
                        "F",
                        "GM",
                        "FORD",
                        # Fintech
                        "SOFI",
                        "UPST",
                        "AFRM",
                        "LENDING",
                        "LC",
                        # Other popular
                        "DIS",
                        "INTC",
                        "CRM",
                        "ORCL",
                        "ADBE",
                        "CSCO",
                        "AVGO",
                        "QCOM",
                        "TXN",
                        "HON",
                    ]

                    # Combine popular stocks with tracked tickers - check up to
                    # 100 tickers
                    tickers_to_check = list(set(popular_stocks + list(all_tickers)[:50]))[:100]
                    print(f"  Checking news for {len(tickers_to_check)} tickers...")

                    news_count = 0
                    for i, ticker in enumerate(tickers_to_check):
                        try:
                            # Add delay to avoid rate limits - every 5 tickers
                            if i > 0 and i % 5 == 0:
                                # Delay every 5 tickers
                                await asyncio.sleep(3.0)

                            news_articles = price_service.get_ticker_news(ticker, limit=10)
                            if news_articles:
                                print(f"  ✅ {ticker}: Found {len(news_articles)} news articles")
                                for article in news_articles:
                                    # Analyze sentiment of news article
                                    sentiment = news_sentiment.analyze(article.get("text", ""))

                                    # Create a mention entry from news article
                                    news_mention = {
                                        "id": article.get(
                                            "id", f"polygon_news_{ticker}_{article.get('published_utc', '')}"
                                        ),
                                        "source": "polygon_news",
                                        "type": "news",
                                        "text": article.get("text", ""),
                                        "title": article.get("title", ""),
                                        "url": article.get("url", ""),
                                        "author_id": None,
                                        "created_at": article.get("published_utc", datetime.utcnow()),
                                        "retweet_count": 0,
                                        "like_count": 0,
                                        "reply_count": 0,
                                        "quote_count": 0,
                                        "tickers": [ticker],
                                        "sentiment": sentiment,
                                        "timestamp": datetime.utcnow(),
                                    }

                                    db_instance.insert_social_mention(news_mention)
                                    anomaly_detector.add_mention(ticker)
                                    news_count += 1
                        except Exception as e:
                            error_msg = str(e)
                            if "rate limit" in error_msg.lower() or "429" in error_msg:
                                print(f"  Polygon rate limit for {ticker} - skipping")
                                await asyncio.sleep(5.0)
                            else:
                                print(f"Error processing news for {ticker}: {e}")
                            continue

                    if news_count > 0:
                        print(f"  ✅ Total: Added {news_count} news articles with sentiment analysis")
                    else:
                        print("  No new news articles this iteration")
                except Exception as e:
                    print(f"Error in Polygon news monitoring: {e}")
                    import traceback

                    traceback.print_exc()

            # Update stock prices every 30 minutes (1800 seconds)
            # Check if 30 minutes have passed since last update
            current_time = time.time()
            time_since_last_update = current_time - last_price_update_time
            should_update_prices = time_since_last_update >= 1800  # 30 minutes in seconds

            # Update stock prices periodically (Polygon mode - every 30 minutes)
            # Fetch prices for ALL stocks, not just a subset
            if all_tickers and price_service.client and should_update_prices:
                try:
                    # Process all tickers in batches to avoid overwhelming the
                    # API
                    all_tickers_list = list(all_tickers)
                    batch_size = 100  # Process 100 at a time
                    total_batches = (len(all_tickers_list) + batch_size - 1) // batch_size

                    for batch_num in range(total_batches):
                        batch_start = batch_num * batch_size
                        batch_end = min((batch_num + 1) * batch_size, len(all_tickers_list))
                        batch_tickers = all_tickers_list[batch_start:batch_end]

                        print(
                            f"  Fetching prices for batch {batch_num + 1}/{total_batches} ({len(batch_tickers)} tickers)..."
                        )

                        # Fetch prices for this batch
                        prices = price_service.get_batch_prices(batch_tickers)
                        for ticker, price_data in prices.items():
                            if price_data:
                                db_instance.insert_stock_price(price_data)

                        # Delay between batches to avoid rate limits
                        if batch_num < total_batches - 1:
                            # 2 second delay between batches
                            await asyncio.sleep(2.0)

                    print(f"  ✅ Updated prices for all {len(all_tickers_list)} stocks")

                    # Update the last price update time
                    last_price_update_time = current_time

                    # Check if it's end of trading day (4:00 PM ET = 9:00 PM UTC during EST, 8:00 PM UTC during EDT)
                    # For simplicity, check if it's between 8:00 PM and 9:00 PM UTC (covers both EST and EDT)
                    from datetime import datetime, timezone

                    now_utc = datetime.now(timezone.utc)
                    hour_utc = now_utc.hour

                    # End of trading day is 4:00 PM ET = 9:00 PM UTC (EST) or 8:00 PM UTC (EDT)
                    # We'll use 8:00 PM UTC as a safe time to capture closing prices
                    if hour_utc == 20:  # 8:00 PM UTC (4:00 PM ET during EDT)
                        print("  📊 End of trading day detected - capturing closing prices...")
                        # Capture closing prices for all stocks
                        for ticker in all_tickers_list:
                            try:
                                # Get the latest price for this ticker
                                latest_price_result = db_instance.conn.execute(
                                    """
                                    SELECT price FROM stock_prices
                                    WHERE ticker = ?
                                    ORDER BY timestamp DESC
                                    LIMIT 1
                                    """,
                                    (ticker,),
                                ).fetchone()

                                if latest_price_result:
                                    closing_price = latest_price_result[0]
                                    today = now_utc.date()

                                    # Store closing price in historical_prices table
                                    # If today's entry exists, update the close price
                                    # Otherwise, create a new entry with close = open = high = low = current price
                                    db_instance.conn.execute(
                                        """
                                        INSERT INTO historical_prices (ticker, date, open, high, low, close, volume)
                                        VALUES (?, ?, ?, ?, ?, ?, ?)
                                        ON CONFLICT (ticker, date) DO UPDATE SET
                                            close = EXCLUDED.close,
                                            high = CASE WHEN EXCLUDED.close > historical_prices.high THEN EXCLUDED.close ELSE historical_prices.high END,
                                            low = CASE WHEN EXCLUDED.close < historical_prices.low THEN EXCLUDED.close ELSE historical_prices.low END
                                        """,
                                        (ticker, today, closing_price, closing_price, closing_price, closing_price, 0),
                                    )
                                    print(f"    ✅ Captured closing price for {ticker}: ${closing_price:.2f}")
                            except Exception as e:
                                pass  # Skip errors for individual tickers

                        print("  ✅ Daily closing prices captured for all stocks")

                    # Also fetch historical prices for tracked tickers (in smaller batches)
                    # Limit to avoid rate limits - process 50 at a time
                    historical_batch_size = 50
                    historical_batches = (len(all_tickers_list) + historical_batch_size - 1) // historical_batch_size
                    for batch_num in range(min(historical_batches, 20)):  # Limit to first 20 batches (1000 stocks max)
                        batch_start = batch_num * historical_batch_size
                        batch_end = min((batch_num + 1) * historical_batch_size, len(all_tickers_list))
                        batch_tickers = all_tickers_list[batch_start:batch_end]

                        for ticker in batch_tickers:
                            try:
                                historical = price_service.get_historical_prices(ticker, days=7)
                                if historical:
                                    db_instance.insert_historical_prices(historical)
                            except Exception as e:
                                pass  # Historical data is optional

                        # Delay between historical batches
                        if batch_num < min(historical_batches, 20) - 1:
                            await asyncio.sleep(1.0)
                except Exception as e:
                    print(f"Error updating stock prices: {e}")

            # Update ticker statistics - process ALL tickers to calculate 24h change
            # This is done less frequently to avoid overwhelming the API
            # Every 3rd iteration (every ~2 minutes)
            if all_tickers and iteration % 3 == 0:
                try:
                    # Get prices for ALL tracked tickers - process in batches
                    all_tickers_list = list(all_tickers)
                    stats_batch_size = 100
                    stats_batches = (len(all_tickers_list) + stats_batch_size - 1) // stats_batch_size

                    processed_count = 0
                    for batch_num in range(stats_batches):
                        batch_start = batch_num * stats_batch_size
                        batch_end = min((batch_num + 1) * stats_batch_size, len(all_tickers_list))
                        batch_tickers = all_tickers_list[batch_start:batch_end]

                        for i, ticker in enumerate(batch_tickers):
                            try:
                                # Add small delay every 25 tickers to avoid
                                # rate limits
                                if i > 0 and i % 25 == 0:
                                    await asyncio.sleep(1.0)

                                current_price = price_service.get_current_price(ticker)

                                # Calculate 24h price change
                                price_change = None
                                price_change_percent = None
                                try:
                                    price_change = price_service.get_price_change(ticker, hours=24)
                                    if price_change:
                                        price_change_percent = price_change.get("change_percent")
                                except Exception as e:
                                    pass  # Price change calculation is optional

                                # Get mention count from database (if any)
                                # Use a simple query instead of getting all
                                # trending tickers
                                mention_count = 0
                                avg_sentiment = 0.0
                                try:
                                    mention_result = db_instance.conn.execute(
                                        """
                                        SELECT COUNT(DISTINCT tm.mention_id) as count,
                                               AVG(sm.sentiment_combined) as avg_sent
                                        FROM ticker_mentions tm
                                        JOIN social_mentions sm ON tm.mention_id = sm.id
                                        WHERE tm.ticker = ? AND tm.timestamp >= CURRENT_TIMESTAMP - INTERVAL '24' HOUR
                                    """,
                                        (ticker,),
                                    ).fetchone()
                                    if mention_result:
                                        mention_count = mention_result[0] or 0
                                        avg_sentiment = mention_result[1] or 0.0
                                except Exception as e:
                                    pass  # Mention count is optional

                                stats = {
                                    "ticker": ticker,
                                    "timestamp": datetime.utcnow(),
                                    "mention_count": mention_count,
                                    "avg_sentiment": avg_sentiment,
                                    "price": current_price["price"] if current_price else None,
                                    "price_change_24h": price_change["change"] if price_change else None,
                                    "price_change_percent_24h": price_change_percent,
                                    "z_score": 0.0,  # Can't calculate without mention history
                                    "is_anomaly": False,
                                }

                                db_instance.insert_ticker_stats(stats)
                                processed_count += 1
                            except Exception as e:
                                pass  # Stats update is optional

                        # Delay between batches
                        if batch_num < stats_batches - 1:
                            await asyncio.sleep(2.0)

                    if processed_count > 0:
                        print(f"Updated stats for {processed_count} tickers")
                except Exception as e:
                    print(f"Error updating ticker stats: {e}")

            # Update more frequently - every 45 seconds to balance speed and rate limits
            # Increased from 30s to allow more stocks to be processed per iteration
            await asyncio.sleep(45)  # Update every 45 seconds to process more stocks

        except Exception as e:
            print(f"Error in monitoring loop: {e}")
            await asyncio.sleep(60)  # Wait longer on error


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
