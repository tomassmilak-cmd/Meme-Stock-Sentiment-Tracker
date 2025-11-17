"""Twitter monitoring service using Tweepy."""

import tweepy
from typing import Iterator, Dict, List
from datetime import datetime
import time
from config import settings
from utils.ticker_extractor import TickerExtractor
from utils.sentiment_analyzer import SentimentAnalyzer


class TwitterMonitor:
    """Monitor Twitter for stock mentions."""

    def __init__(self):
        """Initialize Twitter monitor."""
        if not settings.twitter_bearer_token:
            self.client = None
            print("Warning: Twitter API credentials not configured. Twitter monitoring will be disabled.")
        else:
            self.client = tweepy.Client(bearer_token=settings.twitter_bearer_token, wait_on_rate_limit=True)
        self.ticker_extractor = TickerExtractor()
        self.sentiment_analyzer = SentimentAnalyzer()
        self.processed_ids = set()

    def search_tweets(self, query: str, max_results: int = 100) -> List[Dict]:
        """
        Search for tweets matching query.

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            List of tweet data dictionaries
        """
        if not self.client:
            return []
        try:
            tweets = self.client.search_recent_tweets(
                query=query,
                max_results=min(max_results, 100),
                tweet_fields=["created_at", "author_id", "public_metrics", "text"],
                user_fields=["username"],
            )

            if not tweets.data:
                return []

            results = []
            for tweet in tweets.data:
                # Extract tickers
                tickers = self.ticker_extractor.extract_and_validate(tweet.text)

                if not tickers:
                    continue

                # Analyze sentiment
                sentiment = self.sentiment_analyzer.analyze(tweet.text)

                results.append(
                    {
                        "id": str(tweet.id),
                        "source": "twitter",
                        "type": "tweet",
                        "text": tweet.text,
                        "author_id": str(tweet.author_id) if tweet.author_id else None,
                        "created_at": tweet.created_at,
                        "retweet_count": tweet.public_metrics.get("retweet_count", 0),
                        "like_count": tweet.public_metrics.get("like_count", 0),
                        "reply_count": tweet.public_metrics.get("reply_count", 0),
                        "quote_count": tweet.public_metrics.get("quote_count", 0),
                        "tickers": tickers,
                        "sentiment": sentiment,
                        "timestamp": datetime.utcnow(),
                    }
                )

            return results
        except Exception as e:
            print(f"Error searching tweets: {e}")
            return []

    def search_stock_tickers(self, tickers: List[str], max_results_per_ticker: int = 50) -> List[Dict]:
        """
        Search for tweets mentioning specific stock tickers.

        Args:
            tickers: List of stock tickers to search for
            max_results_per_ticker: Max results per ticker

        Returns:
            List of tweet data dictionaries
        """
        all_tweets = []

        for ticker in tickers:
            # Search for $TICKER or TICKER mentions
            queries = [f"${ticker}", f"{ticker} stock", f"{ticker} to the moon"]

            for query in queries:
                tweets = self.search_tweets(query, max_results_per_ticker)
                all_tweets.extend(tweets)

                # Rate limiting
                time.sleep(1)

        return all_tweets

    def stream_tweets(self, tickers: List[str]) -> Iterator[Dict]:
        """
        Stream tweets mentioning stock tickers (using search in loop).

        Args:
            tickers: List of stock tickers to monitor

        Yields:
            Dictionary with tweet data
        """
        while True:
            for ticker in tickers:
                query = f"${ticker} OR {ticker} stock"
                tweets = self.search_tweets(query, max_results=10)

                for tweet in tweets:
                    if tweet["id"] not in self.processed_ids:
                        self.processed_ids.add(tweet["id"])
                        yield tweet

            # Wait before next iteration
            time.sleep(60)  # Check every minute
