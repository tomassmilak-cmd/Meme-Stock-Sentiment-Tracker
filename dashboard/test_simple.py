"""Simple test dashboard to verify data display."""
import streamlit as st
import requests
import pandas as pd

API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="Test Dashboard", layout="wide")

st.title("Stock Data Test")

# Fetch data
try:
    response = requests.get(f"{API_URL}/api/trending", params={"limit": 100}, timeout=10)
    if response.status_code == 200:
        data = response.json()
        tickers = data.get("tickers", [])
        st.success(f"✅ Fetched {len(tickers)} stocks from API")
        
        if tickers:
            # Create DataFrame
            df = pd.DataFrame(tickers)
            
            # Show raw data
            st.subheader("Raw Data (First 10)")
            st.json(tickers[:10])
            
            # Show simple table
            st.subheader("Simple Table")
            simple_df = df[['ticker', 'latest_price']].copy()
            simple_df.columns = ['Ticker', 'Price']
            st.dataframe(simple_df, use_container_width=True, hide_index=True)
            
            # Show formatted table
            st.subheader("Formatted Table")
            display_df = pd.DataFrame({
                'Ticker': df['ticker'],
                'Price': df['latest_price'].apply(lambda x: f"${x:.2f}" if pd.notna(x) else "N/A"),
                'Mentions': df['mention_count'].apply(lambda x: int(x) if pd.notna(x) else 0),
                'Sentiment': df['avg_sentiment'].apply(lambda x: f"{x:.3f}" if pd.notna(x) else "0.000")
            })
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.error("No tickers in response")
    else:
        st.error(f"API returned status {response.status_code}")
except Exception as e:
    st.error(f"Error: {e}")
    import traceback
    st.exception(e)

