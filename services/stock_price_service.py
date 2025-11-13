"""Stock price service using Polygon.io API."""
from polygon import RESTClient
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from config import settings
import time


class StockPriceService:
    """Fetch real-time and historical stock price data."""
    
    def __init__(self):
        """Initialize Polygon.io client."""
        self.client = RESTClient(settings.polygon_api_key)
    
    def get_current_price(self, ticker: str) -> Optional[Dict]:
        """
        Get current stock price for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Dictionary with current price data or None
        """
        try:
            # Get last trade
            trade = self.client.get_last_trade(ticker)
            
            if not trade:
                return None
            
            # Get current quote
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

