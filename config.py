"""Configuration management for the Meme Stock Sentiment Tracker."""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Reddit API
    reddit_client_id: str
    reddit_client_secret: str
    reddit_user_agent: str = "MemeStockTracker/1.0"
    
    # Twitter API
    twitter_bearer_token: str
    
    # Polygon.io API
    polygon_api_key: str
    
    # Database
    duckdb_path: str = "./data/meme_stocks.duckdb"
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # Reddit subreddit to monitor
    reddit_subreddit: str = "wallstreetbets"
    
    # Twitter search parameters
    twitter_max_results: int = 100
    
    # Sentiment analysis
    sentiment_update_interval: int = 60  # seconds
    
    # Anomaly detection
    z_score_threshold: float = 2.5
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

