"""Database manager for DuckDB."""

import duckdb
from typing import Dict, List, Optional
from datetime import datetime
import os
from config import settings


class DatabaseManager:
    """Manage DuckDB database for real-time analytics."""

    def __init__(self):
        """Initialize database connection (lazy connection)."""
        # Ensure data directory exists
        os.makedirs(os.path.dirname(settings.duckdb_path), exist_ok=True)
        self._conn = None
        self._db_path = settings.duckdb_path
        self._initialized = False

    @property
    def conn(self):
        """Lazy connection - connect only when needed."""
        if self._conn is None:
            # Try to connect with retry logic
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    self._conn = duckdb.connect(self._db_path, read_only=False)
                    if not self._initialized:
                        self._initialize_schema()
                        self._initialized = True
                    break
                except Exception as e:
                    if "lock" in str(e).lower() and attempt < max_retries - 1:
                        import time

                        time.sleep(2)
                        continue
                    else:
                        # If still locked, try read-only mode for queries
                        try:
                            self._conn = duckdb.connect(self._db_path, read_only=True)
                            print("Warning: Database opened in read-only mode due to lock")
                            break
                        except:
                            raise
        return self._conn

    def _initialize_schema(self):
        """Initialize database schema."""
        # Social media posts/comments
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS social_mentions (
                id VARCHAR PRIMARY KEY,
                source VARCHAR,
                type VARCHAR,
                text TEXT,
                title TEXT,
                author VARCHAR,
                score INTEGER,
                num_comments INTEGER,
                created_utc TIMESTAMP,
                url VARCHAR,
                permalink VARCHAR,
                timestamp TIMESTAMP,
                sentiment_combined DOUBLE,
                sentiment_label VARCHAR,
                vader_compound DOUBLE,
                vader_positive DOUBLE,
                vader_neutral DOUBLE,
                vader_negative DOUBLE,
                finbert_positive DOUBLE,
                finbert_negative DOUBLE,
                finbert_neutral DOUBLE
            )
        """
        )

        # Ticker mentions (many-to-many relationship)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ticker_mentions (
                mention_id VARCHAR,
                ticker VARCHAR,
                timestamp TIMESTAMP,
                PRIMARY KEY (mention_id, ticker),
                FOREIGN KEY (mention_id) REFERENCES social_mentions(id)
            )
        """
        )

        # Stock prices
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_prices (
                ticker VARCHAR,
                timestamp TIMESTAMP,
                price DOUBLE,
                bid DOUBLE,
                ask DOUBLE,
                bid_size INTEGER,
                ask_size INTEGER,
                PRIMARY KEY (ticker, timestamp)
            )
        """
        )

        # Historical prices
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS historical_prices (
                ticker VARCHAR,
                date DATE,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT,
                PRIMARY KEY (ticker, date)
            )
        """
        )

        # Ticker statistics (aggregated)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ticker_stats (
                ticker VARCHAR,
                timestamp TIMESTAMP,
                mention_count INTEGER,
                avg_sentiment DOUBLE,
                price DOUBLE,
                price_change_24h DOUBLE,
                price_change_percent_24h DOUBLE,
                z_score DOUBLE,
                is_anomaly BOOLEAN,
                PRIMARY KEY (ticker, timestamp)
            )
        """
        )

        # Create indexes
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_ticker_mentions_ticker ON ticker_mentions(ticker)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_ticker_mentions_timestamp ON ticker_mentions(timestamp)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_social_mentions_timestamp ON social_mentions(timestamp)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_stock_prices_ticker ON stock_prices(ticker, timestamp)")

    def insert_social_mention(self, mention: Dict):
        """Insert a social media mention."""
        sentiment = mention.get("sentiment", {})

        self.conn.execute(
            """
            INSERT OR REPLACE INTO social_mentions (
                id, source, type, text, title, author, score, num_comments,
                created_utc, url, permalink, timestamp,
                sentiment_combined, sentiment_label,
                vader_compound, vader_positive, vader_neutral, vader_negative,
                finbert_positive, finbert_negative, finbert_neutral
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                mention["id"],
                mention["source"],
                mention["type"],
                mention.get("text", ""),
                mention.get("title", ""),
                mention.get("author", ""),
                mention.get("score", 0),
                mention.get("num_comments", 0),
                mention.get("created_utc", mention["timestamp"]),
                mention.get("url", ""),
                mention.get("permalink", ""),
                mention["timestamp"],
                sentiment.get("combined_sentiment", 0.0),
                sentiment.get("sentiment_label", "neutral"),
                sentiment.get("vader", {}).get("compound", 0.0),
                sentiment.get("vader", {}).get("positive", 0.0),
                sentiment.get("vader", {}).get("neutral", 0.0),
                sentiment.get("vader", {}).get("negative", 0.0),
                sentiment.get("finbert", {}).get("positive") if sentiment.get("finbert") else None,
                sentiment.get("finbert", {}).get("negative") if sentiment.get("finbert") else None,
                sentiment.get("finbert", {}).get("neutral") if sentiment.get("finbert") else None,
            ),
        )

        # Insert ticker mentions - use DuckDB conflict syntax
        for ticker in mention.get("tickers", []):
            try:
                # DuckDB syntax: ON CONFLICT (mention_id, ticker) DO NOTHING
                # or use INSERT with ON CONFLICT DO UPDATE
                self.conn.execute(
                    """
                    INSERT INTO ticker_mentions (mention_id, ticker, timestamp)
                    VALUES (?, ?, ?)
                    ON CONFLICT (mention_id, ticker) DO UPDATE SET
                        timestamp = EXCLUDED.timestamp
                """,
                    (mention["id"], ticker.upper(), mention["timestamp"]),
                )
            except Exception as e:
                # If ON CONFLICT doesn't work, try simple INSERT and ignore errors
                try:
                    self.conn.execute(
                        """
                        INSERT INTO ticker_mentions (mention_id, ticker, timestamp)
                VALUES (?, ?, ?)
                    """,
                        (mention["id"], ticker.upper(), mention["timestamp"]),
                    )
                except:
                    pass  # Already exists, ignore

    def insert_stock_price(self, price_data: Dict):
        """Insert stock price data."""
        # Use INSERT ... ON CONFLICT for DuckDB with multiple unique constraints
        self.conn.execute(
            """
            INSERT INTO stock_prices (
                ticker, timestamp, price, bid, ask, bid_size, ask_size
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (ticker, timestamp) DO UPDATE SET
                price = EXCLUDED.price,
                bid = EXCLUDED.bid,
                ask = EXCLUDED.ask,
                bid_size = EXCLUDED.bid_size,
                ask_size = EXCLUDED.ask_size
        """,
            (
                price_data["ticker"],
                price_data.get("timestamp", datetime.utcnow()),
                price_data["price"],
                price_data.get("bid"),
                price_data.get("ask"),
                price_data.get("bid_size"),
                price_data.get("ask_size"),
            ),
        )

    def insert_historical_prices(self, prices: List[Dict]):
        """Insert historical price data."""
        for price in prices:
            try:
                # Use ON CONFLICT with explicit conflict target for composite primary key
                self.conn.execute(
                    """
                    INSERT INTO historical_prices (
                        ticker, date, open, high, low, close, volume
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (ticker, date) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume
                """,
                    (
                        price["ticker"],
                        price["date"].date() if isinstance(price["date"], datetime) else price["date"],
                        price["open"],
                        price["high"],
                        price["low"],
                        price["close"],
                        price["volume"],
                    ),
                )
            except Exception as e:
                # Fallback to INSERT OR REPLACE if ON CONFLICT doesn't work
                try:
                    self.conn.execute(
                        """
                INSERT OR REPLACE INTO historical_prices (
                    ticker, date, open, high, low, close, volume
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                        (
                            price["ticker"],
                            price["date"].date() if isinstance(price["date"], datetime) else price["date"],
                            price["open"],
                            price["high"],
                            price["low"],
                            price["close"],
                            price["volume"],
                        ),
                    )
                except Exception as e2:
                    # If both fail, skip this price entry
                    print(f"Warning: Could not insert historical price for {price.get('ticker', 'UNKNOWN')}: {e2}")
                    continue

    def insert_ticker_stats(self, stats: Dict):
        """Insert ticker statistics."""
        self.conn.execute(
            """
            INSERT OR REPLACE INTO ticker_stats (
                ticker, timestamp, mention_count, avg_sentiment, price,
                price_change_24h, price_change_percent_24h, z_score, is_anomaly
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                stats["ticker"],
                stats.get("timestamp", datetime.utcnow()),
                stats.get("mention_count", 0),
                stats.get("avg_sentiment", 0.0),
                stats.get("price"),
                stats.get("price_change_24h"),
                stats.get("price_change_percent_24h"),
                stats.get("z_score", 0.0),
                stats.get("is_anomaly", False),
            ),
        )

    def get_trending_tickers(self, hours: int = 24, limit: int = 5000) -> List[Dict]:
        """Get trending tickers based on mention volume and sentiment, or stock prices if no mentions."""
        # Limit to prevent timeouts - cap at 5000 (increased from 2000)
        limit = min(limit, 5000)

        # Check if we have any social mentions first
        try:
            count_result = self.conn.execute("SELECT COUNT(*) FROM ticker_mentions").fetchone()
            has_mentions = count_result and count_result[0] > 0
        except Exception as e:
            print(f"Error checking mentions: {e}")
            has_mentions = False

        # Always return all tracked stocks, with mentions if available
        # First, get all tracked stocks from the stock list (all 959 stocks)
        try:
            from utils.stock_list import get_cached_tickers

            all_cached_tickers = get_cached_tickers()  # Get all 959 stocks
            # Only limit if limit is less than total stocks, otherwise return all
            all_tracked_tickers = all_cached_tickers[:limit] if limit < len(all_cached_tickers) else all_cached_tickers
            print(
                f"Returning all {len(all_tracked_tickers)} tracked stocks (with or without prices) out of {len(all_cached_tickers)} total"
            )

            # Get latest prices for all stocks that have them
            price_results = {}
            try:
                price_data = self.conn.execute(
                    """
                    SELECT ticker, price
                    FROM (
                        SELECT ticker, price, timestamp,
                               ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY timestamp DESC) as rn
                        FROM stock_prices
                    ) ranked
                    WHERE rn = 1
                """
                ).fetchall()
                price_results = {row[0].upper(): float(row[1]) if row[1] is not None else None for row in price_data}
                print(
                    f"Found prices for {len([p for p in price_results.values() if p is not None])} stocks out of {len(all_tracked_tickers)} total"
                )
            except Exception as e:
                print(f"Error fetching prices: {e}")

            # Get mention counts if available
            mention_results = {}
            twitter_mentions = {}
            polygon_mentions = {}
            sentiment_results = {}
            if has_mentions:
                try:
                    mention_data = self.conn.execute(
                        f"""
            SELECT 
                tm.ticker,
                COUNT(DISTINCT tm.mention_id) as mention_count,
                AVG(sm.sentiment_combined) as avg_sentiment,
                            COUNT(DISTINCT CASE WHEN sm.source = 'twitter' THEN tm.mention_id END) as twitter_mentions,
                            COUNT(DISTINCT CASE WHEN sm.source = 'polygon_news' THEN tm.mention_id END) as polygon_mentions
            FROM ticker_mentions tm
            JOIN social_mentions sm ON tm.mention_id = sm.id
                        WHERE tm.timestamp >= CURRENT_TIMESTAMP - INTERVAL '{hours}' HOUR
            GROUP BY tm.ticker
                    """
                    ).fetchall()

                    for row in mention_data:
                        ticker_upper = row[0].upper()
                        mention_results[ticker_upper] = row[1] if row[1] else 0
                        sentiment_results[ticker_upper] = float(row[2]) if row[2] else 0.0
                        twitter_mentions[ticker_upper] = row[3] if row[3] else 0
                        polygon_mentions[ticker_upper] = row[4] if row[4] else 0
                    print(f"Found mentions for {len(mention_results)} stocks")
                except Exception as e:
                    print(f"Error fetching mentions: {e}")

            # Get 24h price changes from ticker_stats (most reliable)
            price_change_24h = {}
            try:
                # Get 24h change from ticker_stats (latest entry per ticker)
                stats_data = self.conn.execute(
                    """
                    SELECT ticker, price_change_percent_24h
                    FROM (
                        SELECT ticker, price_change_percent_24h, timestamp,
                               ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY timestamp DESC) as rn
                        FROM ticker_stats
                        WHERE price_change_percent_24h IS NOT NULL
                    ) ranked
                    WHERE rn = 1
                """
                ).fetchall()
                for row in stats_data:
                    price_change_24h[row[0]] = row[1]

                # Also try to calculate from historical_prices if not in stats
                # Get latest prices and compare with prices from 24h ago
                try:
                    historical_data = self.conn.execute(
                        """
                        SELECT 
                            ticker,
                            MAX(CASE WHEN date >= CURRENT_DATE - INTERVAL '1' DAY THEN close END) as current_price,
                            MAX(CASE WHEN date < CURRENT_DATE - INTERVAL '1' DAY 
                                 AND date >= CURRENT_DATE - INTERVAL '2' DAY THEN close END) as price_24h_ago
                        FROM historical_prices
                        WHERE date >= CURRENT_DATE - INTERVAL '2' DAY
                        GROUP BY ticker
                    """
                    ).fetchall()

                    for row in historical_data:
                        ticker, current_price, price_24h_ago = row
                        # Only use if we don't already have data for this ticker
                        if ticker not in price_change_24h and current_price and price_24h_ago and price_24h_ago > 0:
                            change_percent = ((current_price - price_24h_ago) / price_24h_ago) * 100
                            price_change_24h[ticker] = change_percent
                except Exception as e2:
                    print(f"Error calculating 24h change from historical: {e2}")

            except Exception as e:
                print(f"Error fetching 24h change: {e}")

            # Build result list with all tracked stocks - ensure tickers are uppercase for matching
            result = []
            for ticker in all_tracked_tickers:
                ticker_upper = ticker.upper()
                result.append(
                    {
                        "ticker": ticker_upper,
                        "mention_count": int(mention_results.get(ticker_upper, 0)),
                        "avg_sentiment": float(sentiment_results.get(ticker_upper, 0.0)),
                        "latest_price": price_results.get(ticker_upper),  # Can be None if no price
                        "price_change_24h": price_change_24h.get(ticker_upper),  # 24h change if available
                        "twitter_mentions": int(twitter_mentions.get(ticker_upper, 0)),
                        "polygon_mentions": int(polygon_mentions.get(ticker_upper, 0)),
                    }
                )

            # Sort by mention count descending (stocks with mentions first), then by ticker alphabetically
            # This ensures stocks with mentions appear at the top, followed by all others alphabetically
            result.sort(key=lambda x: (x["mention_count"] == 0, -x["mention_count"], x["ticker"]))

            print(f"Returning {len(result)} stocks to API")
            return result

        except Exception as e:
            print(f"Error in get_trending_tickers: {e}")
            import traceback

            traceback.print_exc()
            # Fallback: return empty list
            return []

    def get_ticker_sentiment_trend(self, ticker: str, hours: int = 24) -> List[Dict]:
        """Get sentiment trend for a ticker over time."""
        query = f"""
            SELECT 
                DATE_TRUNC('hour', tm.timestamp) as hour,
                COUNT(DISTINCT tm.mention_id) as mention_count,
                AVG(sm.sentiment_combined) as avg_sentiment,
                COUNT(DISTINCT CASE WHEN sm.source = 'twitter' THEN tm.mention_id END) as twitter_mentions,
                COUNT(DISTINCT CASE WHEN sm.source = 'polygon_news' THEN tm.mention_id END) as polygon_mentions
            FROM ticker_mentions tm
            JOIN social_mentions sm ON tm.mention_id = sm.id
            WHERE tm.ticker = '{ticker.upper()}' AND tm.timestamp >= CURRENT_TIMESTAMP - INTERVAL '{hours}' HOUR
            GROUP BY hour
            ORDER BY hour
        """

        try:
            result = self.conn.execute(query).fetchall()
        except Exception as e:
            print(f"Error in get_ticker_sentiment_trend: {e}")
            return []

        return [
            {
                "hour": row[0],
                "mention_count": row[1] if row[1] else 0,
                "avg_sentiment": row[2] if row[2] else 0.0,
                "twitter_mentions": row[3] if row[3] else 0,
                "polygon_mentions": row[4] if row[4] else 0,
            }
            for row in result
        ]

    def get_ticker_stats(self, ticker: str, hours: int = 24) -> Dict:
        """Get comprehensive stats for a specific ticker."""
        ticker_upper = ticker.upper()
        stats = {
            "ticker": ticker_upper,
            "mention_count": 0,
            "twitter_mentions": 0,
            "polygon_mentions": 0,
            "avg_sentiment": 0.0,
            "latest_price": None,
            "price_change_24h": None,
            "price_change_percent_24h": None,
        }

        try:
            # Get mention counts and sentiment directly from database
            mention_data = self.conn.execute(
                f"""
                SELECT 
                    COUNT(DISTINCT tm.mention_id) as mention_count,
                    AVG(sm.sentiment_combined) as avg_sentiment,
                    COUNT(DISTINCT CASE WHEN sm.source = 'twitter' THEN tm.mention_id END) as twitter_mentions,
                    COUNT(DISTINCT CASE WHEN sm.source = 'polygon_news' THEN tm.mention_id END) as polygon_mentions
                FROM ticker_mentions tm
                JOIN social_mentions sm ON tm.mention_id = sm.id
                WHERE tm.ticker = '{ticker_upper}' 
                AND tm.timestamp >= CURRENT_TIMESTAMP - INTERVAL '{hours}' HOUR
            """
            ).fetchone()

            if mention_data:
                stats["mention_count"] = mention_data[0] if mention_data[0] else 0
                stats["avg_sentiment"] = float(mention_data[1]) if mention_data[1] else 0.0
                stats["twitter_mentions"] = mention_data[2] if mention_data[2] else 0
                stats["polygon_mentions"] = mention_data[3] if mention_data[3] else 0
        except Exception as e:
            print(f"Error getting mention stats for {ticker_upper}: {e}")

        try:
            # Get latest price from database
            price_data = self.conn.execute(
                """
                SELECT price, timestamp
                FROM (
                    SELECT price, timestamp,
                           ROW_NUMBER() OVER (ORDER BY timestamp DESC) as rn
                    FROM stock_prices
                    WHERE ticker = ?
                ) ranked
                WHERE rn = 1
            """,
                (ticker_upper,),
            ).fetchone()

            if price_data:
                stats["latest_price"] = float(price_data[0]) if price_data[0] else None
        except Exception as e:
            print(f"Error getting price for {ticker_upper}: {e}")

        try:
            # Get 24h price change from ticker_stats
            price_change_data = self.conn.execute(
                """
                SELECT price_change_24h, price_change_percent_24h
                FROM (
                    SELECT price_change_24h, price_change_percent_24h, timestamp,
                           ROW_NUMBER() OVER (ORDER BY timestamp DESC) as rn
                    FROM ticker_stats
                    WHERE ticker = ? AND price_change_24h IS NOT NULL
                ) ranked
                WHERE rn = 1
            """,
                (ticker_upper,),
            ).fetchone()

            if price_change_data:
                stats["price_change_24h"] = float(price_change_data[0]) if price_change_data[0] else None
                stats["price_change_percent_24h"] = float(price_change_data[1]) if price_change_data[1] else None
        except Exception as e:
            print(f"Error getting price change for {ticker_upper}: {e}")

        return stats

    def get_ticker_price_history(self, ticker: str, days: int = 7) -> List[Dict]:
        """Get price history for a ticker."""
        query = f"""
            SELECT date, open, high, low, close, volume
            FROM historical_prices
            WHERE ticker = '{ticker.upper()}' AND date >= CURRENT_DATE - INTERVAL '{days}' DAYS
            ORDER BY date
        """

        try:
            result = self.conn.execute(query).fetchall()
        except Exception as e:
            print(f"Error in get_ticker_price_history: {e}")
            return []

        return [
            {"date": row[0], "open": row[1], "high": row[2], "low": row[3], "close": row[4], "volume": row[5]}
            for row in result
        ]

    def close(self):
        """Close database connection."""
        if self._conn:
            try:
                self._conn.close()
            except Exception as e:
                print(f"Warning: Error closing database connection: {e}")
            finally:
                self._conn = None
