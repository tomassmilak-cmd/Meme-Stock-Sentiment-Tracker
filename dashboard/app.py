"""Streamlit dashboard for Meme Stock Sentiment Tracker."""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
import time
from typing import Dict, List

# Configuration
API_URL = "http://localhost:8000"  # Change if API is hosted elsewhere

st.set_page_config(
    page_title="Meme Stock Sentiment Tracker",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    </style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=30)
def fetch_trending_tickers(hours: int = 24, limit: int = 20) -> List[Dict]:
    """Fetch trending tickers from API."""
    try:
        response = requests.get(f"{API_URL}/api/trending", params={"hours": hours, "limit": limit})
        if response.status_code == 200:
            return response.json().get("tickers", [])
    except Exception as e:
        st.error(f"Error fetching trending tickers: {e}")
    return []


@st.cache_data(ttl=30)
def fetch_ticker_stats(ticker: str, hours: int = 24) -> Dict:
    """Fetch stats for a specific ticker."""
    try:
        response = requests.get(f"{API_URL}/api/ticker/{ticker}/stats", params={"hours": hours})
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.error(f"Error fetching ticker stats: {e}")
    return {}


@st.cache_data(ttl=30)
def fetch_ticker_sentiment(ticker: str, hours: int = 24) -> List[Dict]:
    """Fetch sentiment trend for a ticker."""
    try:
        response = requests.get(f"{API_URL}/api/ticker/{ticker}/sentiment", params={"hours": hours})
        if response.status_code == 200:
            return response.json().get("trend", [])
    except Exception as e:
        st.error(f"Error fetching sentiment: {e}")
    return []


@st.cache_data(ttl=60)
def fetch_ticker_price_history(ticker: str, days: int = 7) -> List[Dict]:
    """Fetch price history for a ticker."""
    try:
        response = requests.get(f"{API_URL}/api/ticker/{ticker}/price-history", params={"days": days})
        if response.status_code == 200:
            return response.json().get("history", [])
    except Exception as e:
        st.error(f"Error fetching price history: {e}")
    return []


@st.cache_data(ttl=30)
def fetch_anomalies(hours: int = 24) -> List[Dict]:
    """Fetch detected anomalies."""
    try:
        response = requests.get(f"{API_URL}/api/anomalies", params={"hours": hours})
        if response.status_code == 200:
            return response.json().get("anomalies", [])
    except Exception as e:
        st.error(f"Error fetching anomalies: {e}")
    return []


def main():
    """Main dashboard application."""
    st.markdown('<h1 class="main-header">📈 Meme Stock Sentiment Tracker</h1>', unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Settings")
        
        time_window = st.selectbox(
            "Time Window",
            options=[1, 6, 12, 24, 48, 72],
            index=3,
            format_func=lambda x: f"{x} hours"
        )
        
        auto_refresh = st.checkbox("Auto Refresh", value=True)
        refresh_interval = st.slider("Refresh Interval (seconds)", 10, 300, 30)
        
        if st.button("🔄 Refresh Now"):
            st.cache_data.clear()
            st.rerun()
        
        st.markdown("---")
        st.markdown("### 📊 Data Sources")
        st.markdown("- Reddit (r/WallStreetBets)")
        st.markdown("- Twitter")
        st.markdown("- Polygon.io (Stock Prices)")
    
    # Main content
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Leaderboard", "📈 Ticker Analysis", "🚨 Anomalies", "ℹ️ About"])
    
    with tab1:
        st.header("🔥 Trending Tickers Leaderboard")
        
        trending = fetch_trending_tickers(hours=time_window, limit=50)
        
        if trending:
            df = pd.DataFrame(trending)
            
            # Format data
            df['avg_sentiment'] = df['avg_sentiment'].round(3)
            df['latest_price'] = df['latest_price'].apply(lambda x: f"${x:.2f}" if x and pd.notna(x) else "N/A")
            df['price_change_24h'] = df['price_change_24h'].apply(
                lambda x: f"{x:+.2f}%" if x and pd.notna(x) else "N/A"
            )
            
            # Display metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Tickers", len(df))
            with col2:
                st.metric("Total Mentions", int(df['mention_count'].sum()))
            with col3:
                st.metric("Avg Sentiment", f"{df['avg_sentiment'].mean():.3f}")
            with col4:
                positive_tickers = len(df[df['avg_sentiment'] > 0.1])
                st.metric("Positive Tickers", positive_tickers)
            
            # Leaderboard table
            st.subheader("Top Trending Stocks")
            display_df = df[['ticker', 'mention_count', 'avg_sentiment', 'latest_price', 'price_change_24h']].copy()
            display_df.columns = ['Ticker', 'Mentions', 'Avg Sentiment', 'Price', '24h Change']
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            # Visualizations
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Mention Volume")
                fig = px.bar(
                    df.head(20),
                    x='ticker',
                    y='mention_count',
                    title="Top 20 by Mention Count",
                    labels={'ticker': 'Ticker', 'mention_count': 'Mentions'}
                )
                fig.update_xaxes(tickangle=45)
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.subheader("Sentiment Distribution")
                fig = px.histogram(
                    df,
                    x='avg_sentiment',
                    nbins=30,
                    title="Sentiment Score Distribution",
                    labels={'avg_sentiment': 'Average Sentiment', 'count': 'Number of Tickers'}
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No trending tickers found. Make sure monitoring is active.")
    
    with tab2:
        st.header("📈 Individual Ticker Analysis")
        
        # Get list of tickers
        trending = fetch_trending_tickers(hours=time_window, limit=100)
        tickers = [t['ticker'] for t in trending] if trending else []
        
        if tickers:
            selected_ticker = st.selectbox("Select Ticker", tickers)
        else:
            selected_ticker = st.text_input("Enter Ticker Symbol", "AAPL").upper()
        
        if selected_ticker:
            stats = fetch_ticker_stats(selected_ticker, hours=time_window)
            sentiment_trend = fetch_ticker_sentiment(selected_ticker, hours=time_window)
            price_history = fetch_ticker_price_history(selected_ticker, days=7)
            
            if stats:
                # Key metrics
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    price = stats.get('current_price', {}).get('price', 'N/A')
                    st.metric("Current Price", f"${price:.2f}" if isinstance(price, (int, float)) else price)
                
                with col2:
                    mention_count = stats.get('mention_count', 0)
                    st.metric("Mentions", mention_count)
                
                with col3:
                    avg_sentiment = stats.get('avg_sentiment', 0.0)
                    st.metric("Avg Sentiment", f"{avg_sentiment:.3f}")
                
                with col4:
                    price_change = stats.get('price_change', {})
                    change_pct = price_change.get('change_percent', 0) if price_change else 0
                    st.metric("24h Change", f"{change_pct:+.2f}%")
                
                # Sentiment trend
                if sentiment_trend:
                    st.subheader("Sentiment Trend Over Time")
                    df_sentiment = pd.DataFrame(sentiment_trend)
                    df_sentiment['hour'] = pd.to_datetime(df_sentiment['hour'])
                    
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=df_sentiment['hour'],
                        y=df_sentiment['avg_sentiment'],
                        mode='lines+markers',
                        name='Sentiment',
                        line=dict(color='blue', width=2)
                    ))
                    fig.add_hline(y=0, line_dash="dash", line_color="gray", annotation_text="Neutral")
                    fig.update_layout(
                        title=f"Sentiment Trend for {selected_ticker}",
                        xaxis_title="Time",
                        yaxis_title="Sentiment Score",
                        hovermode='x unified'
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Mention volume over time
                    fig2 = px.bar(
                        df_sentiment,
                        x='hour',
                        y='mention_count',
                        title=f"Mention Volume Over Time for {selected_ticker}",
                        labels={'hour': 'Time', 'mention_count': 'Mentions'}
                    )
                    st.plotly_chart(fig2, use_container_width=True)
                
                # Price history
                if price_history:
                    st.subheader("Price History")
                    df_price = pd.DataFrame(price_history)
                    df_price['date'] = pd.to_datetime(df_price['date'])
                    
                    fig = go.Figure()
                    fig.add_trace(go.Candlestick(
                        x=df_price['date'],
                        open=df_price['open'],
                        high=df_price['high'],
                        low=df_price['low'],
                        close=df_price['close'],
                        name=selected_ticker
                    ))
                    fig.update_layout(
                        title=f"Price History for {selected_ticker}",
                        xaxis_title="Date",
                        yaxis_title="Price ($)",
                        xaxis_rangeslider_visible=False
                    )
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning(f"No data available for {selected_ticker}")
    
    with tab3:
        st.header("🚨 Anomaly Detection")
        st.markdown("Tickers with unusual mention volume (Z-score > 2.5)")
        
        anomalies = fetch_anomalies(hours=time_window)
        
        if anomalies:
            df_anomalies = pd.DataFrame(anomalies)
            
            st.metric("Anomalies Detected", len(df_anomalies))
            
            # Display anomalies
            display_df = df_anomalies[['ticker', 'mention_count', 'z_score', 'direction']].copy()
            display_df.columns = ['Ticker', 'Mentions', 'Z-Score', 'Direction']
            display_df['Z-Score'] = display_df['Z-Score'].round(2)
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            # Visualization
            fig = px.bar(
                df_anomalies,
                x='ticker',
                y='z_score',
                color='direction',
                title="Anomaly Z-Scores",
                labels={'ticker': 'Ticker', 'z_score': 'Z-Score', 'direction': 'Direction'},
                color_discrete_map={'surge': 'green', 'drop': 'red'}
            )
            fig.update_xaxes(tickangle=45)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No anomalies detected in the current time window.")
    
    with tab4:
        st.header("ℹ️ About")
        st.markdown("""
        ### Meme Stock Sentiment Tracker
        
        A real-time sentiment analysis system that monitors social media platforms
        (Reddit and Twitter) for stock ticker mentions and correlates them with
        market movements.
        
        #### Features:
        - **Real-time Monitoring**: Streams posts from r/WallStreetBets and Twitter
        - **Dual Sentiment Analysis**: Uses VADER (social media) and FinBERT (finance)
        - **Anomaly Detection**: Identifies unusual mention volume using Z-scores
        - **Price Correlation**: Integrates real-time stock prices via Polygon.io
        - **Live Dashboard**: Interactive Streamlit dashboard with visualizations
        
        #### Tech Stack:
        - Python, FastAPI, Streamlit
        - DuckDB for real-time analytics
        - HuggingFace Transformers (FinBERT)
        - PRAW (Reddit), Tweepy (Twitter)
        - Polygon.io API (Stock prices)
        - Docker for containerization
        """)
    
    # Auto-refresh
    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()


if __name__ == "__main__":
    main()

