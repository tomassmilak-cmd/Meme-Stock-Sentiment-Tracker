"""Stock price service using Massive.com API (formerly Polygon.io)."""
from polygon import RESTClient
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from config import settings
import time


class StockPriceService:
    """Fetch real-time and historical stock price data."""
    
    def __init__(self):
        """Initialize Massive.com API client (formerly Polygon.io)."""
        if not settings.polygon_api_key:
            self.client = None
            print("Warning: Massive.com API key not configured. Stock price fetching will be disabled.")
        else:
            # Use the new Massive.com API endpoint (api.massive.com)
            # The old api.polygon.io endpoint still works, but using the new one is recommended
            self.client = RESTClient(
                api_key=settings.polygon_api_key,
                base="https://api.massive.com"  # New Massive.com endpoint
            )
    
    def get_current_price(self, ticker: str) -> Optional[Dict]:
        """
        Get current stock price for a ticker.
        Uses aggregates endpoint (available on free tier) as fallback if real-time is not available.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Dictionary with current price data or None
        """
        if not self.client:
            return None
        
        # Try real-time data first (if available on plan)
        try:
            trade = self.client.get_last_trade(ticker)
            if trade:
                try:
                    quote = self.client.get_last_quote(ticker)
                except:
                    quote = None
            
            return {
                'ticker': ticker,
                'price': trade.price,
                'timestamp': datetime.fromtimestamp(trade.timestamp / 1000) if hasattr(trade, 'timestamp') else datetime.utcnow(),
                'bid': quote.bid if quote else None,
                'ask': quote.ask if quote else None,
                'bid_size': quote.bid_size if quote else None,
                'ask_size': quote.ask_size if quote else None
            }
        except Exception as e:
            error_msg = str(e)
            # If not authorized for real-time, fall back to aggregates
            if "NOT_AUTHORIZED" in error_msg or "not entitled" in error_msg.lower():
                pass  # Will try aggregates below
            else:
                print(f"Error fetching real-time price for {ticker}: {e}")
        
        # Fallback to aggregates (available on free tier)
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=1)
            
            aggs = self.client.get_aggs(
                ticker=ticker,
                multiplier=1,
                timespan="day",
                from_=start_date.strftime("%Y-%m-%d"),
                to=end_date.strftime("%Y-%m-%d"),
                limit=1
            )
            
            if aggs and len(aggs) > 0:
                latest = aggs[-1]  # Get most recent
                return {
                    'ticker': ticker,
                    'price': latest.close,
                    'timestamp': datetime.fromtimestamp(latest.timestamp / 1000) if hasattr(latest, 'timestamp') else datetime.utcnow(),
                    'bid': None,
                    'ask': None,
                    'bid_size': None,
                    'ask_size': None,
                    'source': 'delayed'  # Indicate this is delayed data
                }
        except Exception as e:
            error_msg = str(e)
            if "Unknown API Key" in error_msg or "Invalid API key" in error_msg:
                print(f"ERROR: Invalid Massive.com API key. Please check your POLYGON_API_KEY in .env file")
                print(f"Get your API key from: https://massive.com/dashboard/api-keys")
            else:
                print(f"Error fetching price for {ticker}: {e}")
        
        return None
    
    def get_batch_prices(self, tickers: List[str]) -> Dict[str, Dict]:
        """
        Get current prices for multiple tickers.
        
        Args:
            tickers: List of stock ticker symbols
            
        Returns:
            Dictionary mapping ticker to price data
        """
        prices = {}
        
        for ticker in tickers:
            price_data = self.get_current_price(ticker)
            if price_data:
                prices[ticker] = price_data
            time.sleep(0.1)  # Rate limiting
        
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
        if not self.client:
            return []
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            aggs = self.client.get_aggs(
                ticker=ticker,
                multiplier=1,
                timespan="day",
                from_=start_date.strftime("%Y-%m-%d"),
                to=end_date.strftime("%Y-%m-%d")
            )
            
            prices = []
            for agg in aggs:
                prices.append({
                    'ticker': ticker,
                    'date': datetime.fromtimestamp(agg.timestamp / 1000),
                    'open': agg.open,
                    'high': agg.high,
                    'low': agg.low,
                    'close': agg.close,
                    'volume': agg.volume
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
        if not self.client:
            return None
        try:
            current = self.get_current_price(ticker)
            if not current:
                return None
            
            # Get price from hours ago
            end_date = datetime.now()
            start_date = end_date - timedelta(hours=hours)
            
            # Get minute-level data for recent price
            try:
                aggs = self.client.get_aggs(
                    ticker=ticker,
                    multiplier=1,
                    timespan="minute",
                    from_=start_date.strftime("%Y-%m-%d"),
                    to=end_date.strftime("%Y-%m-%d"),
                    limit=1
                )
                
                if aggs and len(aggs) > 0:
                    previous_price = aggs[0].close
                else:
                    previous_price = current['price']
            except:
                previous_price = current['price']
            
            current_price = current['price']
            
            change = current_price - previous_price
            change_percent = (change / previous_price) * 100 if previous_price else 0
            
            return {
                'ticker': ticker,
                'current_price': current_price,
                'previous_price': previous_price,
                'change': change,
                'change_percent': change_percent,
                'hours': hours
            }
        except Exception as e:
            print(f"Error calculating price change for {ticker}: {e}")
            return None

