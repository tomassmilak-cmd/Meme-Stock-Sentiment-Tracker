"""Reddit monitoring service using PRAW."""
import praw
from typing import Iterator, Dict, List
from datetime import datetime
import time
from config import settings
from utils.ticker_extractor import TickerExtractor
from utils.sentiment_analyzer import SentimentAnalyzer


class RedditMonitor:
    """Monitor Reddit posts and comments for stock mentions."""
    
    def __init__(self):
        """Initialize Reddit monitor."""
        if not settings.reddit_client_id or not settings.reddit_client_secret:
            self.reddit = None
            self.subreddit = None
            print("Warning: Reddit API credentials not configured. Reddit monitoring will be disabled.")
        else:
            self.reddit = praw.Reddit(
                client_id=settings.reddit_client_id,
                client_secret=settings.reddit_client_secret,
                user_agent=settings.reddit_user_agent
            )
            self.subreddit = self.reddit.subreddit(settings.reddit_subreddit)
        self.ticker_extractor = TickerExtractor()
        self.sentiment_analyzer = SentimentAnalyzer()
        self.processed_ids = set()
    
    def stream_posts(self) -> Iterator[Dict]:
        """
        Stream new posts from subreddit.
        
        Yields:
            Dictionary with post data and extracted tickers
        """
        if not self.subreddit:
            return
        for submission in self.subreddit.stream.submissions(skip_existing=True):
            if submission.id in self.processed_ids:
                continue
            
            self.processed_ids.add(submission.id)
            
            # Extract tickers from title and selftext
            text = f"{submission.title} {submission.selftext or ''}"
            tickers = self.ticker_extractor.extract_and_validate(text)
            
            if not tickers:
                continue
            
            # Analyze sentiment
            sentiment = self.sentiment_analyzer.analyze(text)
            
            post_data = {
                'id': submission.id,
                'source': 'reddit',
                'type': 'post',
                'title': submission.title,
                'text': submission.selftext or '',
                'author': str(submission.author) if submission.author else 'deleted',
                'score': submission.score,
                'num_comments': submission.num_comments,
                'created_utc': datetime.fromtimestamp(submission.created_utc),
                'url': submission.url,
                'permalink': f"https://reddit.com{submission.permalink}",
                'tickers': tickers,
                'sentiment': sentiment,
                'timestamp': datetime.utcnow()
            }
            
            yield post_data
    
    def stream_comments(self) -> Iterator[Dict]:
        """
        Stream new comments from subreddit.
        
        Yields:
            Dictionary with comment data and extracted tickers
        """
        if not self.subreddit:
            return
        for comment in self.subreddit.stream.comments(skip_existing=True):
            if comment.id in self.processed_ids:
                continue
            
            self.processed_ids.add(comment.id)
            
            # Extract tickers
            tickers = self.ticker_extractor.extract_and_validate(comment.body)
            
            if not tickers:
                continue
            
            # Analyze sentiment
            sentiment = self.sentiment_analyzer.analyze(comment.body)
            
            comment_data = {
                'id': comment.id,
                'source': 'reddit',
                'type': 'comment',
                'text': comment.body,
                'author': str(comment.author) if comment.author else 'deleted',
                'score': comment.score,
                'created_utc': datetime.fromtimestamp(comment.created_utc),
                'permalink': f"https://reddit.com{comment.permalink}",
                'tickers': tickers,
                'sentiment': sentiment,
                'timestamp': datetime.utcnow()
            }
            
            yield comment_data
    
    def get_recent_posts(self, limit: int = 100) -> List[Dict]:
        """
        Get recent posts from subreddit.
        
        Args:
            limit: Number of posts to retrieve
            
        Returns:
            List of post data dictionaries
        """
        if not self.subreddit:
            return []
        posts = []
        
        for submission in self.subreddit.new(limit=limit):
            text = f"{submission.title} {submission.selftext or ''}"
            tickers = self.ticker_extractor.extract_and_validate(text)
            
            if not tickers:
                continue
            
            sentiment = self.sentiment_analyzer.analyze(text)
            
            posts.append({
                'id': submission.id,
                'source': 'reddit',
                'type': 'post',
                'title': submission.title,
                'text': submission.selftext or '',
                'author': str(submission.author) if submission.author else 'deleted',
                'score': submission.score,
                'num_comments': submission.num_comments,
                'created_utc': datetime.fromtimestamp(submission.created_utc),
                'url': submission.url,
                'permalink': f"https://reddit.com{submission.permalink}",
                'tickers': tickers,
                'sentiment': sentiment,
                'timestamp': datetime.utcnow()
            })
        
        return posts

