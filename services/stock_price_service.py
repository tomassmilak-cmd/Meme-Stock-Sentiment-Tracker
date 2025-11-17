"""Stock price service using Yahoo Finance API."""

import yfinance as yf
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import time


class StockPriceService:
    """Fetch real-time and historical stock price data using Yahoo Finance."""

    def __init__(self):
        """Initialize Yahoo Finance client (no API key required)."""
        self.client = True  # Yahoo Finance doesn't need a client object, but we keep this for compatibility
        print("✅ Yahoo Finance initialized - no API key required")

    def get_current_price(self, ticker: str) -> Optional[Dict]:
        """
        Get current stock price for a ticker.
        Uses history as primary method (most reliable, least rate limited).

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dictionary with current price data or None
        """
        try:
            stock = yf.Ticker(ticker)
            current_price = None
            
            # Method 1: Try history first (most reliable, least rate limited)
            # Use daily data which is more stable
            try:
                # Try 5-day history to get most recent close
                hist = stock.history(period="5d", interval="1d")
                if not hist.empty:
                    current_price = float(hist['Close'].iloc[-1])
                else:
                    # Fallback to 1-month if 5-day fails
                    hist = stock.history(period="1mo", interval="1d")
                    if not hist.empty:
                        current_price = float(hist['Close'].iloc[-1])
            except Exception as e:
                error_str = str(e)
                # If rate limited, wait a bit and try once more
                if "429" in error_str or "Too Many Requests" in error_str:
                    time.sleep(2)  # Wait 2 seconds
                    try:
                        hist = stock.history(period="5d", interval="1d")
                        if not hist.empty:
                            current_price = float(hist['Close'].iloc[-1])
                    except:
                        pass  # Give up on history
            
            # Method 2: Try fast_info (faster but may be rate limited)
            if current_price is None:
                try:
                    time.sleep(0.5)  # Small delay before fast_info
                    fast_info = stock.fast_info
                    current_price = fast_info.get('lastPrice') or fast_info.get('regularMarketPrice')
                    if current_price:
                        current_price = float(current_price)
                except Exception as e:
                    # fast_info may not be available or rate limited
                    pass
            
            # Method 3: Try info as last resort (most rate limited)
            if current_price is None:
                try:
                    time.sleep(1)  # Longer delay before info
                    info = stock.info
                    current_price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose')
                    if current_price:
                        current_price = float(current_price)
                except Exception as e:
                    # Rate limited or other error - don't print to avoid spam
                    pass
            
            if current_price is None:
                return None

            # Get bid/ask if available (optional, may not be available)
            bid = None
            ask = None
            bid_size = None
            ask_size = None
            try:
                fast_info = stock.fast_info
                bid = fast_info.get('bid')
                ask = fast_info.get('ask')
            except:
                pass  # fast_info may not be available, that's okay

            return {
                "ticker": ticker.upper(),
                "price": float(current_price),
                "timestamp": datetime.utcnow(),
                "bid": float(bid) if bid else None,
                "ask": float(ask) if ask else None,
                "bid_size": int(bid_size) if bid_size else None,
                "ask_size": int(ask_size) if ask_size else None,
            }
        except Exception as e:
            # Don't print errors for rate limiting (too noisy)
            error_str = str(e)
            if "429" not in error_str and "Too Many Requests" not in error_str:
                print(f"Error fetching current price for {ticker}: {e}")
            return None

    def get_batch_prices(self, tickers: List[str]) -> Dict[str, Dict]:
        """
        Get current prices for multiple tickers.
        Uses individual fetches with delays to avoid rate limiting.

        Args:
            tickers: List of stock ticker symbols

        Returns:
            Dictionary mapping ticker to price data
        """
        prices = {}
        
        # Use individual fetches with delays to avoid rate limiting
        # Yahoo Finance batch downloads can be unreliable when rate limited
        for i, ticker in enumerate(tickers):
            try:
                price_data = self.get_current_price(ticker)
                if price_data:
                    prices[ticker.upper()] = price_data
                
                # Add delay to avoid rate limiting (longer delays to prevent 429 errors)
                if i > 0:
                    if i % 5 == 0:
                        time.sleep(2.0)  # Longer delay every 5 tickers
                    elif i % 2 == 0:
                        time.sleep(1.0)  # Medium delay every 2 tickers
                    else:
                        time.sleep(0.5)  # Short delay between tickers
            except Exception as e:
                # Skip this ticker if it fails
                continue

        return prices

    def get_historical_prices(self, ticker: str, days: int = 7) -> List[Dict]:
        """
        Get historical price data for a ticker.

        Args:
            ticker: Stock ticker symbol
            days: Number of days of history

        Returns:
            List of price data dictionaries
        """
        try:
            stock = yf.Ticker(ticker)
            # Get historical data
            hist = stock.history(period=f"{days}d")
            
            if hist.empty:
                return []

            prices = []
            for date, row in hist.iterrows():
                prices.append({
                    "ticker": ticker.upper(),
                    "date": date.to_pydatetime() if hasattr(date, 'to_pydatetime') else date,
                    "open": float(row['Open']) if 'Open' in row else None,
                    "high": float(row['High']) if 'High' in row else None,
                    "low": float(row['Low']) if 'Low' in row else None,
                    "close": float(row['Close']) if 'Close' in row else None,
                    "volume": int(row['Volume']) if 'Volume' in row else 0,
                })

            return prices
        except Exception as e:
            print(f"Error fetching historical prices for {ticker}: {e}")
            return []

    def get_price_change(self, ticker: str, hours: int = 24) -> Optional[Dict]:
        """
        Get price change over specified hours.

        Args:
            ticker: Stock ticker symbol
            hours: Number of hours to look back

        Returns:
            Dictionary with price change data or None
        """
        try:
            stock = yf.Ticker(ticker)
            
            # Get current price
            current = self.get_current_price(ticker)
            if not current:
                return None
            
            current_price = current["price"]
            
            # Get price from hours ago
            # For intraday data, we'll use minute-level data
            if hours <= 24:
                # Get intraday data for recent hours
                period = "1d"
                interval = "1h" if hours >= 1 else "1m"
            else:
                # For longer periods, use daily data
                period = f"{hours//24 + 1}d"
                interval = "1d"
            
            try:
                hist = stock.history(period=period, interval=interval)
                if not hist.empty and len(hist) > 1:
                    # Get price from approximately hours ago
                    # For hourly data, get the price from hours hours ago
                    if hours <= len(hist):
                        previous_price = hist['Close'].iloc[-hours] if hours < len(hist) else hist['Close'].iloc[0]
                    else:
                        previous_price = hist['Close'].iloc[0]
                else:
                    previous_price = current_price
            except:
                previous_price = current_price

            change = current_price - previous_price
            change_percent = (change / previous_price) * 100 if previous_price else 0

            return {
                "ticker": ticker.upper(),
                "current_price": current_price,
                "previous_price": previous_price,
                "change": change,
                "change_percent": change_percent,
                "hours": hours,
            }
        except Exception as e:
            print(f"Error calculating price change for {ticker}: {e}")
            return None

    def get_ticker_news(self, ticker: str, limit: int = 5) -> List[Dict]:
        """
        Get news articles for a ticker from Yahoo Finance.

        Args:
            ticker: Stock ticker symbol
            limit: Maximum number of articles to return

        Returns:
            List of news article dictionaries
        """
        try:
            stock = yf.Ticker(ticker)
            news = stock.news
            
            if not news:
                return []

            articles = []
            for item in news[:limit]:
                try:
                    article = {
                        "id": item.get("uuid", f"news_{ticker}_{hash(item.get('title', ''))}"),
                        "title": item.get("title", ""),
                        "text": item.get("summary", "") or item.get("link", "") or "",
                        "url": item.get("link", ""),
                        "published_utc": datetime.fromtimestamp(item.get("providerPublishTime", 0)) if item.get("providerPublishTime") else datetime.utcnow(),
                        "author": None,  # Yahoo Finance news doesn't always have author
                        "publisher": item.get("publisher", ""),
                    }
                    articles.append(article)
                except Exception as e:
                    print(f"Error parsing news item for {ticker}: {e}")
                    continue

            return articles
        except Exception as e:
            print(f"Error fetching news for {ticker}: {e}")
            return []
