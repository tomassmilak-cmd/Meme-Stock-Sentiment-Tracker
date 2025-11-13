"""Anomaly detection using Z-scores for mention volume."""
from typing import Dict, List
import numpy as np
from collections import defaultdict
from datetime import datetime, timedelta


class AnomalyDetector:
    """Detect anomalies in stock mention volume using Z-scores."""
    
    def __init__(self, z_threshold: float = 2.5, window_hours: int = 24):
        """
        Initialize anomaly detector.
        
        Args:
            z_threshold: Z-score threshold for anomaly detection
            window_hours: Time window in hours for calculating statistics
        """
        self.z_threshold = z_threshold
        self.window_hours = window_hours
        self.mention_history: Dict[str, List[tuple]] = defaultdict(list)
        # Store (timestamp, count) tuples
    
    def add_mention(self, ticker: str, timestamp: datetime = None):
        """
        Record a mention for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            timestamp: Timestamp of the mention (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        self.mention_history[ticker].append((timestamp, 1))
        
        # Clean old data (keep only last window_hours)
        cutoff = timestamp - timedelta(hours=self.window_hours)
        self.mention_history[ticker] = [
            (ts, count) for ts, count in self.mention_history[ticker]
            if ts >= cutoff
        ]
    
    def get_mention_counts(self, ticker: str, window_minutes: int = 60) -> List[int]:
        """
        Get mention counts for a ticker in recent time windows.
        
        Args:
            ticker: Stock ticker symbol
            window_minutes: Size of each time window in minutes
            
        Returns:
            List of mention counts per window
        """
        if ticker not in self.mention_history:
            return []
        
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=self.window_hours)
        
        # Filter recent mentions
        recent_mentions = [
            ts for ts, _ in self.mention_history[ticker]
            if ts >= cutoff
        ]
        
        if not recent_mentions:
            return []
        
        # Group by time windows
        window_counts = defaultdict(int)
        for ts in recent_mentions:
            window_key = ts.replace(second=0, microsecond=0)
            window_key = window_key.replace(
                minute=(window_key.minute // window_minutes) * window_minutes
            )
            window_counts[window_key] += 1
        
        return list(window_counts.values())
    
    def calculate_z_score(self, ticker: str, current_count: int, window_minutes: int = 60) -> float:
        """
        Calculate Z-score for current mention count.
        
        Args:
            ticker: Stock ticker symbol
            current_count: Current mention count
            window_minutes: Time window size in minutes
            
        Returns:
            Z-score value
        """
        counts = self.get_mention_counts(ticker, window_minutes)
        
        if len(counts) < 2:
            # Not enough data for Z-score calculation
            return 0.0
        
        mean = np.mean(counts)
        std = np.std(counts)
        
        if std == 0:
            return 0.0
        
        z_score = (current_count - mean) / std
        return z_score
    
    def is_anomaly(self, ticker: str, current_count: int, window_minutes: int = 60) -> bool:
        """
        Check if current mention count is an anomaly.
        
        Args:
            ticker: Stock ticker symbol
            current_count: Current mention count
            window_minutes: Time window size in minutes
            
        Returns:
            True if anomaly detected
        """
        z_score = self.calculate_z_score(ticker, current_count, window_minutes)
        return abs(z_score) >= self.z_threshold
    
    def detect_anomalies(self, ticker_counts: Dict[str, int], window_minutes: int = 60) -> Dict[str, Dict]:
        """
        Detect anomalies across multiple tickers.
        
        Args:
            ticker_counts: Dictionary of ticker -> current mention count
            window_minutes: Time window size in minutes
            
        Returns:
            Dictionary of ticker -> anomaly info
        """
        anomalies = {}
        
        for ticker, count in ticker_counts.items():
            z_score = self.calculate_z_score(ticker, count, window_minutes)
            is_anomaly = abs(z_score) >= self.z_threshold
            
            if is_anomaly:
                anomalies[ticker] = {
                    'ticker': ticker,
                    'mention_count': count,
                    'z_score': z_score,
                    'is_anomaly': True,
                    'direction': 'surge' if z_score > 0 else 'drop'
                }
        
        return anomalies

