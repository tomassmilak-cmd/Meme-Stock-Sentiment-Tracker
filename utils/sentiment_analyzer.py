"""Sentiment analysis using VADER and FinBERT."""
from typing import Dict, Optional
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import numpy as np


class SentimentAnalyzer:
    """Dual sentiment analysis using VADER (social media) and FinBERT (finance)."""
    
    def __init__(self):
        """Initialize sentiment analyzers."""
        # VADER for social media sentiment
        self.vader = SentimentIntensityAnalyzer()
        
        # FinBERT for financial sentiment
        try:
            self.finbert_tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
            self.finbert_model = AutoModelForSequenceClassification.from_pretrained(
                "ProsusAI/finbert"
            )
            self.finbert_model.eval()
            self.finbert_available = True
        except Exception as e:
            print(f"Warning: FinBERT model could not be loaded: {e}")
            self.finbert_available = False
            self.finbert_tokenizer = None
            self.finbert_model = None
    
    def analyze_vader(self, text: str) -> Dict[str, float]:
        """
        Analyze sentiment using VADER.
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary with sentiment scores
        """
        scores = self.vader.polarity_scores(text)
        return {
            'compound': scores['compound'],
            'positive': scores['pos'],
            'neutral': scores['neu'],
            'negative': scores['neg']
        }
    
    def analyze_finbert(self, text: str) -> Optional[Dict[str, float]]:
        """
        Analyze sentiment using FinBERT.
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary with sentiment scores or None if model unavailable
        """
        if not self.finbert_available:
            return None
        
        try:
            # Tokenize and encode
            inputs = self.finbert_tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding=True
            )
            
            # Get predictions
            with torch.no_grad():
                outputs = self.finbert_model(**inputs)
                predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
            
            # FinBERT labels: positive, negative, neutral
            labels = ['positive', 'negative', 'neutral']
            scores = predictions[0].numpy()
            
            return {
                'positive': float(scores[0]),
                'negative': float(scores[1]),
                'neutral': float(scores[2])
            }
        except Exception as e:
            print(f"Error in FinBERT analysis: {e}")
            return None
    
    def analyze(self, text: str) -> Dict[str, any]:
        """
        Perform dual sentiment analysis.
        
        Args:
            text: Text to analyze
            
        Returns:
            Combined sentiment analysis results
        """
        vader_scores = self.analyze_vader(text)
        finbert_scores = self.analyze_finbert(text)
        
        result = {
            'vader': vader_scores,
            'finbert': finbert_scores,
            'text': text
        }
        
        # Calculate combined sentiment score
        if finbert_scores:
            # Weighted average: 40% VADER, 60% FinBERT
            vader_compound = vader_scores['compound']
            finbert_net = finbert_scores['positive'] - finbert_scores['negative']
            combined = 0.4 * vader_compound + 0.6 * finbert_net
        else:
            combined = vader_scores['compound']
        
        result['combined_sentiment'] = combined
        result['sentiment_label'] = self._classify_sentiment(combined)
        
        return result
    
    def _classify_sentiment(self, score: float) -> str:
        """Classify sentiment score into label."""
        if score >= 0.1:
            return 'positive'
        elif score <= -0.1:
            return 'negative'
        else:
            return 'neutral'

