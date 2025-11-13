"""Extract and validate US stock tickers from text."""
import re
from typing import List, Set, Optional


class TickerExtractor:
    """Extract and validate US stock tickers from social media posts."""
    
    # Common stock ticker patterns (1-5 uppercase letters)
    TICKER_PATTERN = re.compile(r'\$?([A-Z]{1,5})\b')
    
    # Common false positives to exclude
    FALSE_POSITIVES = {
        'A', 'I', 'AM', 'AN', 'AS', 'AT', 'BE', 'BY', 'DO', 'GO', 'HA', 'HE',
        'IF', 'IN', 'IS', 'IT', 'ME', 'MY', 'NO', 'OF', 'ON', 'OR', 'SO', 'TO',
        'UP', 'US', 'WE', 'YOU', 'THE', 'AND', 'FOR', 'ARE', 'BUT', 'NOT',
        'ALL', 'CAN', 'HER', 'WAS', 'ONE', 'OUR', 'OUT', 'DAY', 'GET', 'HAS',
        'HIM', 'HIS', 'HOW', 'ITS', 'MAY', 'NEW', 'NOW', 'OLD', 'SEE', 'TWO',
        'WHO', 'BOY', 'DID', 'ITS', 'LET', 'PUT', 'SAY', 'SHE', 'TOO', 'USE',
        'YTD', 'CEO', 'CFO', 'IPO', 'ETF', 'SEC', 'IRS', 'FDA', 'USD', 'GDP',
        'EPS', 'PE', 'ROI', 'AI', 'ML', 'API', 'URL', 'PDF', 'USA', 'UK',
        'EU', 'AM', 'PM', 'EST', 'PST', 'GMT', 'UTC'
    }
    
    def __init__(self):
        """Initialize ticker extractor."""
        self._valid_tickers: Optional[Set[str]] = None
    
    def extract_tickers(self, text: str) -> Set[str]:
        """
        Extract potential stock tickers from text.
        
        Args:
            text: Input text to search for tickers
            
        Returns:
            Set of potential ticker symbols
        """
        if not text:
            return set()
        
        # Find all matches
        matches = self.TICKER_PATTERN.findall(text.upper())
        
        # Filter out false positives
        tickers = {ticker for ticker in matches if ticker not in self.FALSE_POSITIVES}
        
        return tickers
    
    def is_valid_ticker(self, ticker: str) -> bool:
        """
        Check if a ticker is likely valid.
        
        Args:
            ticker: Ticker symbol to validate
            
        Returns:
            True if ticker appears valid
        """
        ticker = ticker.upper().strip()
        
        # Basic validation
        if not ticker or len(ticker) > 5:
            return False
        
        if ticker in self.FALSE_POSITIVES:
            return False
        
        # Must be all uppercase letters
        if not ticker.isalpha():
            return False
        
        return True
    
    def extract_and_validate(self, text: str) -> List[str]:
        """
        Extract and validate tickers from text.
        
        Args:
            text: Input text
            
        Returns:
            List of validated ticker symbols
        """
        tickers = self.extract_tickers(text)
        validated = [t for t in tickers if self.is_valid_ticker(t)]
        return sorted(list(set(validated)))

