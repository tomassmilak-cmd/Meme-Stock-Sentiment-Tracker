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
        self.conn.execute("""
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
        """)
        
        # Ticker mentions (many-to-many relationship)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS ticker_mentions (
                mention_id VARCHAR,
                ticker VARCHAR,
                timestamp TIMESTAMP,
                PRIMARY KEY (mention_id, ticker),
                FOREIGN KEY (mention_id) REFERENCES social_mentions(id)
            )
        """)
        
        # Stock prices
        self.conn.execute("""
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
        """)
        
        # Historical prices
        self.conn.execute("""
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
        """)
        
        # Ticker statistics (aggregated)
        self.conn.execute("""
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
        """)
        
        # Create indexes
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_ticker_mentions_ticker ON ticker_mentions(ticker)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_ticker_mentions_timestamp ON ticker_mentions(timestamp)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_social_mentions_timestamp ON social_mentions(timestamp)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_stock_prices_ticker ON stock_prices(ticker, timestamp)")
    
    def insert_social_mention(self, mention: Dict):
        """Insert a social media mention."""
        sentiment = mention.get('sentiment', {})
        
        self.conn.execute("""
            INSERT OR REPLACE INTO social_mentions (
                id, source, type, text, title, author, score, num_comments,
                created_utc, url, permalink, timestamp,
                sentiment_combined, sentiment_label,
                vader_compound, vader_positive, vader_neutral, vader_negative,
                finbert_positive, finbert_negative, finbert_neutral
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            mention['id'],
            mention['source'],
            mention['type'],
            mention.get('text', ''),
            mention.get('title', ''),
            mention.get('author', ''),
            mention.get('score', 0),
            mention.get('num_comments', 0),
            mention.get('created_utc', mention['timestamp']),
            mention.get('url', ''),
            mention.get('permalink', ''),
            mention['timestamp'],
            sentiment.get('combined_sentiment', 0.0),
            sentiment.get('sentiment_label', 'neutral'),
            sentiment.get('vader', {}).get('compound', 0.0),
            sentiment.get('vader', {}).get('positive', 0.0),
            sentiment.get('vader', {}).get('neutral', 0.0),
            sentiment.get('vader', {}).get('negative', 0.0),
            sentiment.get('finbert', {}).get('positive') if sentiment.get('finbert') else None,
            sentiment.get('finbert', {}).get('negative') if sentiment.get('finbert') else None,
            sentiment.get('finbert', {}).get('neutral') if sentiment.get('finbert') else None
        ))
        
        # Insert ticker mentions
        for ticker in mention.get('tickers', []):
            self.conn.execute("""
                INSERT OR REPLACE INTO ticker_mentions (mention_id, ticker, timestamp)
                VALUES (?, ?, ?)
            """, (mention['id'], ticker, mention['timestamp']))
    
    def insert_stock_price(self, price_data: Dict):
        """Insert stock price data."""
        # Use INSERT ... ON CONFLICT for DuckDB with multiple unique constraints
        self.conn.execute("""
            INSERT INTO stock_prices (
                ticker, timestamp, price, bid, ask, bid_size, ask_size
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (ticker, timestamp) DO UPDATE SET
                price = EXCLUDED.price,
                bid = EXCLUDED.bid,
                ask = EXCLUDED.ask,
                bid_size = EXCLUDED.bid_size,
                ask_size = EXCLUDED.ask_size
        """, (
            price_data['ticker'],
            price_data.get('timestamp', datetime.utcnow()),
            price_data['price'],
            price_data.get('bid'),
            price_data.get('ask'),
            price_data.get('bid_size'),
            price_data.get('ask_size')
        ))
    
    def insert_historical_prices(self, prices: List[Dict]):
        """Insert historical price data."""
        for price in prices:
            self.conn.execute("""
                INSERT OR REPLACE INTO historical_prices (
                    ticker, date, open, high, low, close, volume
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                price['ticker'],
                price['date'].date() if isinstance(price['date'], datetime) else price['date'],
                price['open'],
                price['high'],
                price['low'],
                price['close'],
                price['volume']
            ))
    
    def insert_ticker_stats(self, stats: Dict):
        """Insert ticker statistics."""
        self.conn.execute("""
            INSERT OR REPLACE INTO ticker_stats (
                ticker, timestamp, mention_count, avg_sentiment, price,
                price_change_24h, price_change_percent_24h, z_score, is_anomaly
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            stats['ticker'],
            stats.get('timestamp', datetime.utcnow()),
            stats.get('mention_count', 0),
            stats.get('avg_sentiment', 0.0),
            stats.get('price'),
            stats.get('price_change_24h'),
            stats.get('price_change_percent_24h'),
            stats.get('z_score', 0.0),
            stats.get('is_anomaly', False)
        ))
    
    def get_trending_tickers(self, hours: int = 24, limit: int = 20) -> List[Dict]:
        """Get trending tickers based on mention volume and sentiment, or stock prices if no mentions."""
        # Check if we have any social mentions first
        try:
            count_result = self.conn.execute("SELECT COUNT(*) FROM ticker_mentions").fetchone()
            has_mentions = count_result and count_result[0] > 0
        except:
            has_mentions = False
        
        if has_mentions:
            # Use proper DuckDB INTERVAL syntax
            query = f"""
                SELECT 
                    tm.ticker,
                    COUNT(DISTINCT tm.mention_id) as mention_count,
                    AVG(sm.sentiment_combined) as avg_sentiment,
                    MAX(sp.price) as latest_price,
                    MAX(ts.price_change_percent_24h) as price_change_24h
                FROM ticker_mentions tm
                JOIN social_mentions sm ON tm.mention_id = sm.id
                LEFT JOIN stock_prices sp ON tm.ticker = sp.ticker
                LEFT JOIN ticker_stats ts ON tm.ticker = ts.ticker
                WHERE tm.timestamp >= CURRENT_TIMESTAMP - INTERVAL '{hours}' HOUR
                GROUP BY tm.ticker
                ORDER BY mention_count DESC, avg_sentiment DESC
                LIMIT {limit}
            """
        else:
            # Fallback to stock prices only (Polygon mode) - get latest price per ticker
            query = f"""
                SELECT 
                    ticker,
                    0 as mention_count,
                    0.0 as avg_sentiment,
                    price as latest_price,
                    NULL as price_change_24h
                FROM (
                    SELECT ticker, price, timestamp,
                           ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY timestamp DESC) as rn
                    FROM stock_prices
                    WHERE timestamp >= CURRENT_TIMESTAMP - INTERVAL '{hours}' HOUR
                ) ranked
                WHERE rn = 1
                ORDER BY ticker
                LIMIT {limit}
            """
        
        try:
            result = self.conn.execute(query).fetchall()
            print(f"get_trending_tickers: Found {len(result)} tickers")
        except Exception as e:
            print(f"Error in get_trending_tickers query: {e}")
            # Fallback: get any tickers with prices (simplest possible query)
            try:
                query_fallback = f"""
                    SELECT ticker, 0, 0.0, price, NULL
                    FROM stock_prices
                    WHERE timestamp >= CURRENT_TIMESTAMP - INTERVAL '{hours}' HOUR
                    ORDER BY timestamp DESC
                    LIMIT {limit}
                """
                result = self.conn.execute(query_fallback).fetchall()
                print(f"Fallback query found {len(result)} tickers")
            except Exception as e2:
                print(f"Fallback query also failed: {e2}")
                return []
        
        return [
            {
                'ticker': row[0],
                'mention_count': row[1] if row[1] else 0,
                'avg_sentiment': row[2] if row[2] else 0.0,
                'latest_price': row[3],
                'price_change_24h': row[4]
            }
            for row in result
        ]
    
    def get_ticker_sentiment_trend(self, ticker: str, hours: int = 24) -> List[Dict]:
        """Get sentiment trend for a ticker over time."""
        query = f"""
            SELECT 
                DATE_TRUNC('hour', tm.timestamp) as hour,
                COUNT(*) as mention_count,
                AVG(sm.sentiment_combined) as avg_sentiment
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
                'hour': row[0],
                'mention_count': row[1],
                'avg_sentiment': row[2] if row[2] else 0.0
            }
            for row in result
        ]
    
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
            {
                'date': row[0],
                'open': row[1],
                'high': row[2],
                'low': row[3],
                'close': row[4],
                'volume': row[5]
            }
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

