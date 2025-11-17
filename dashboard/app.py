"""Professional stock sentiment dashboard."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
import time
from typing import Dict, List

# Configuration
API_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="Stock Sentiment Tracker", page_icon="📊", layout="wide", initial_sidebar_state="collapsed"
)

# Professional CSS styling
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 600;
        color: #1e293b;
        text-align: center;
        margin-bottom: 2rem;
        padding: 1rem 0;
        border-bottom: 2px solid #e2e8f0;
    }
    .metric-container {
        background-color: #ffffff;
        padding: 1.5rem;
        border-radius: 8px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        margin: 0.5rem 0;
    }
    </style>
""",
    unsafe_allow_html=True,
)


def fetch_trending_tickers(hours: int = 24, limit: int = 5000) -> List[Dict]:
    """Fetch trending tickers from API - no caching for immediate updates."""
    try:
        # Reduce limit to prevent timeouts - cap at 5000 (increased from 2000)
        limit = min(limit, 5000)

        response = requests.get(
            f"{API_URL}/api/trending",
            params={"hours": hours, "limit": limit},
            timeout=30,  # Increased timeout from 15 to 30 seconds
        )
        if response.status_code == 200:
            data = response.json()
            tickers = data.get("tickers", [])
            return tickers
        else:
            st.warning(f"API returned status code: {response.status_code}")
            return []
    except requests.exceptions.Timeout:
        st.warning(
            "⏳ API request timed out. The server may be processing a large amount of data. Please wait and refresh."
        )
        return []
    except requests.exceptions.ConnectionError:
        st.error("❌ Cannot connect to API. Please ensure the API server is running on http://127.0.0.1:8000")
        return []
    except Exception as e:
        st.error(f"❌ Error fetching trending tickers: {e}")
    return []


@st.cache_data(ttl=10)  # Reduced TTL to get fresher data
def fetch_ticker_stats(ticker: str, hours: int = 24) -> Dict:
    """Fetch stats for a specific ticker."""
    try:
        response = requests.get(
            f"{API_URL}/api/ticker/{ticker}/stats",
            params={"hours": hours},
            timeout=30,  # Increased timeout to handle slow API responses
        )
        if response.status_code == 200:
            data = response.json()
            # The API returns nested structure, flatten it for dashboard
            # Extract price from current_price if needed
            if "latest_price" not in data or data.get("latest_price") is None:
                current_price = data.get("current_price", {})
                if isinstance(current_price, dict):
                    data["latest_price"] = current_price.get("price")
                elif isinstance(current_price, (int, float)):
                    data["latest_price"] = current_price

            # Extract price change from price_change if needed
            if "price_change_percent_24h" not in data or data.get("price_change_percent_24h") is None:
                price_change = data.get("price_change", {})
                if isinstance(price_change, dict):
                    data["price_change_percent_24h"] = price_change.get("change_percent")
                    data["price_change_24h"] = price_change.get("change")

            # If still no price, try to get from database via trending endpoint
            if not data.get("latest_price"):
                try:
                    trending_response = requests.get(
                        f"{API_URL}/api/trending", params={"limit": 5000, "hours": hours}, timeout=10
                    )
                    if trending_response.status_code == 200:
                        trending_data = trending_response.json()
                        for ticker_data in trending_data.get("tickers", []):
                            if ticker_data.get("ticker") == ticker.upper():
                                if ticker_data.get("latest_price"):
                                    data["latest_price"] = ticker_data.get("latest_price")
                                break
                except:
                    pass  # Fallback failed, continue with what we have

            # Ensure all fields are present
            if "twitter_mentions" not in data:
                data["twitter_mentions"] = 0
            if "polygon_mentions" not in data:
                data["polygon_mentions"] = 0
            if "mention_count" not in data:
                data["mention_count"] = data.get("twitter_mentions", 0) + data.get("polygon_mentions", 0)
            if "avg_sentiment" not in data:
                data["avg_sentiment"] = 0.0
            return data
        else:
            return {}
    except Exception as e:
        return {}


@st.cache_data(ttl=10)  # Reduced TTL to get fresher data
def fetch_ticker_sentiment(ticker: str, hours: int = 24) -> List[Dict]:
    """Fetch sentiment trend for a ticker."""
    try:
        response = requests.get(
            f"{API_URL}/api/ticker/{ticker}/sentiment",
            params={"hours": hours},
            timeout=30,  # Increased timeout to handle slow API responses
        )
        if response.status_code == 200:
            trend = response.json().get("trend", [])
            # Ensure all trend entries have required fields
            for entry in trend:
                if "twitter_mentions" not in entry:
                    entry["twitter_mentions"] = 0
                if "polygon_mentions" not in entry:
                    entry["polygon_mentions"] = 0
                if "mention_count" not in entry:
                    entry["mention_count"] = entry.get("twitter_mentions", 0) + entry.get("polygon_mentions", 0)
            return trend
        return []
    except Exception as e:
        return []


@st.cache_data(ttl=60)
def fetch_ticker_price_history(ticker: str, days: int = 7) -> List[Dict]:
    """Fetch price history for a ticker."""
    try:
        response = requests.get(
            f"{API_URL}/api/ticker/{ticker}/price-history",
            params={"days": days},
            timeout=30,  # Increased timeout to handle slow API responses
        )
        if response.status_code == 200:
            history = response.json().get("history", [])
            # Ensure all history entries have required fields
            for entry in history:
                for col in ["open", "high", "low", "close", "volume"]:
                    if col not in entry:
                        entry[col] = None
            return history
        return []
    except Exception as e:
        return []


def main():
    """Main dashboard application."""
    st.markdown('<h1 class="main-header">Stock Sentiment Tracker</h1>', unsafe_allow_html=True)

    # Sidebar
    with st.sidebar:
        st.header("Settings")

        time_window = st.selectbox(
            "Time Window", options=[1, 6, 12, 24, 48, 72], index=3, format_func=lambda x: f"{x} hours"
        )

        auto_refresh = st.checkbox("Auto Refresh", value=False)
        if auto_refresh:
            refresh_interval = st.slider("Refresh Interval (seconds)", 10, 300, 30)
        else:
            refresh_interval = 30

        if st.button("🔄 Refresh Now"):
            st.cache_data.clear()
            st.rerun()

        st.markdown("---")
        st.markdown("**Data Sources**")
        st.markdown("- Massive.com (Stock Prices)")
        st.markdown("- News Articles")
        st.markdown("- Twitter (if configured)")
        st.markdown("- Reddit (if configured)")

    # Initialize session state for selected ticker
    if "selected_ticker" not in st.session_state:
        st.session_state.selected_ticker = ""

    # Tabs
    tab1, tab2 = st.tabs(["📊 Stocks Being Discussed", "🔍 Search Individual Stock"])

    with tab1:
        st.header("Stocks Being Discussed")

        # Fetch data with loading indicator - don't block if API is slow
        try:
            # Use a placeholder to show loading state
            loading_placeholder = st.empty()
            with loading_placeholder.container():
                st.info("⏳ Loading stock data...")

            # Fetch data (with timeout handled in function)
            trending = fetch_trending_tickers(hours=time_window, limit=5000)  # Increased to 5000 to show more stocks

            # Clear loading placeholder
            loading_placeholder.empty()
        except Exception as e:
            st.error(f"Error fetching data: {e}")
            trending = []

        if not trending:
            st.warning("⚠️ No stock data available yet.")
            st.info("💡 This could mean:")
            st.info("   1. The API is still starting up (wait 10-20 seconds and refresh)")
            st.info("   2. Data collection hasn't started yet (click 'Start Data Collection' below)")
            st.info("   3. The API is processing a large amount of data (wait a bit longer)")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("🚀 Start Data Collection", key="start_collection"):
                    try:
                        with st.spinner("Starting data collection..."):
                            # Start tracking popular stocks
                            try:
                                track_response = requests.post(f"{API_URL}/api/track-popular", timeout=60)
                                if track_response.status_code == 200:
                                    st.success("✅ Price data collection started!")
                                else:
                                    st.warning(f"Track response: {track_response.status_code}")
                            except requests.exceptions.Timeout:
                                st.info("⏳ Data collection started (may take a minute to process)")
                            except Exception as e:
                                st.warning(f"Track error: {e}")

                            # Start monitoring for mentions and sentiment
                            try:
                                monitor_response = requests.post(f"{API_URL}/api/monitor/start", timeout=15)
                                if monitor_response.status_code == 200:
                                    st.success("✅ Monitoring started - collecting mentions and sentiment!")
                            except Exception as e:
                                st.info("Monitoring may already be running")

                            st.info(
                                "⏳ Collecting data from Twitter and Polygon. Wait 30-60 seconds, then refresh the page."
                            )
                            time.sleep(2)
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

            with col2:
                if st.button("🔄 Refresh Now", key="refresh_now"):
                    st.rerun()

            return

        # Show all stocks - always display all stocks, with mentions if available
        stocks_with_mentions = [t for t in trending if t.get("mention_count", 0) > 0]

        # Count stocks with valid prices - check if latest_price exists and is valid
        stocks_with_prices = []
        for t in trending:
            price = t.get("latest_price")
            if price is not None:
                try:
                    # Handle both numeric and string prices
                    if pd.notna(price):
                        price_val = float(price) if not isinstance(price, (int, float)) else price
                        if price_val > 0:
                            stocks_with_prices.append(t)
                except (ValueError, TypeError):
                    pass

        # Create DataFrame from trending stocks
        df = pd.DataFrame(trending) if trending else pd.DataFrame()

        if stocks_with_mentions:
            # Show all stocks, but highlight those with mentions
            st.success(
                f"✅ Found {len(stocks_with_mentions)} stocks with mentions! Showing all {len(trending)} stocks."
            )
        else:
            # Show all stocks, mention that monitoring is happening
            if stocks_with_prices:
                st.info(
                    f"📊 Showing all {len(trending)} stocks. {len(stocks_with_prices)} stocks have price data. Monitoring for mentions and sentiment..."
                )
            else:
                st.warning(
                    f"📊 Showing all {len(trending)} stocks. No price data available yet. Starting data collection..."
                )
                # Auto-start price collection if no prices available
                try:
                    track_response = requests.post(f"{API_URL}/api/track-popular", timeout=10)
                    if track_response.status_code == 200:
                        st.info("🔄 Started price data collection - prices will appear shortly")
                except:
                    pass  # Might already be running

            # Auto-start monitoring if not already running
            try:
                monitor_response = requests.post(f"{API_URL}/api/monitor/start", timeout=5)
                if monitor_response.status_code == 200:
                    st.info("🔄 Started monitoring in background - mentions will appear shortly")
            except:
                pass  # Monitoring might already be running

        if len(df) == 0:
            st.error("⚠️ DataFrame is empty after processing")
            st.json({"trending_count": len(trending), "sample": trending[:3] if trending else []})
            return

            # Display metrics
            col1, col2, col3, col4 = st.columns(4)
            if stocks_with_mentions:
                st.metric("Stocks Discussed", len(df))
            else:
                st.metric("Total Stocks", len(df))
            with col2:
                total_mentions = int(df["mention_count"].sum()) if "mention_count" in df.columns else 0
            if stocks_with_mentions:
                st.metric("Total Mentions", total_mentions)
            else:
                avg_price = df["latest_price"].mean() if "latest_price" in df.columns else 0
                st.metric("Avg Price", f"${avg_price:.2f}" if avg_price > 0 else "N/A")
            with col3:
                if stocks_with_mentions:
                    avg_sentiment = df["avg_sentiment"].mean() if "avg_sentiment" in df.columns else 0.0
                    st.metric("Avg Sentiment", f"{avg_sentiment:.3f}")
                else:
                    st.metric("Status", "Collecting Data")
            with col4:
                if stocks_with_mentions:
                    positive_count = len(df[df["avg_sentiment"] > 0.1]) if "avg_sentiment" in df.columns else 0
                    st.metric("Positive Stocks", positive_count)
                else:
                    st.metric("Mentions", "Coming Soon")

        st.markdown("---")

        # Sort options
        if stocks_with_mentions:
            sort_by = st.selectbox(
                "Sort By",
                [
                    "Mentions (Most)",
                    "Mentions (Least)",
                    "Price (High)",
                    "Price (Low)",
                    "Sentiment (High)",
                    "Sentiment (Low)",
                    "Ticker",
                ],
                index=0,
            )
        else:
            sort_by = st.selectbox("Sort By", ["Price (High)", "Price (Low)", "Ticker"], index=0)

        # Sort DataFrame
        if stocks_with_mentions:
            sort_map = {
                "Mentions (Most)": ("mention_count", False),
                "Mentions (Least)": ("mention_count", True),
                "Price (High)": ("latest_price", False),
                "Price (Low)": ("latest_price", True),
                "Sentiment (High)": ("avg_sentiment", False),
                "Sentiment (Low)": ("avg_sentiment", True),
                "Ticker": ("ticker", True),
            }
        else:
            sort_map = {
                "Price (High)": ("latest_price", False),
                "Price (Low)": ("latest_price", True),
                "Ticker": ("ticker", True),
            }

        sort_col, ascending = sort_map.get(sort_by, ("ticker", True))

        if sort_col in df.columns:
            df = df.sort_values(by=sort_col, ascending=ascending, na_position="last")

        # Format for display - ensure we always have Price column
        display_df = df.copy()

        # Always show Price - format as currency
        if "latest_price" in df.columns:

            def format_price(x):
                """Safely format price value."""
                try:
                    # Handle None, NaN, empty string, or 0
                    if pd.isna(x) or x is None or x == "" or str(x).lower() == "none":
                        return "N/A"
                    # Convert to float and check if valid
                    price_float = float(x) if not isinstance(x, (int, float)) else x
                    if price_float > 0:
                        return f"${price_float:.2f}"
                    else:
                        return "N/A"
                except (ValueError, TypeError, AttributeError):
                    return "N/A"

            display_df["Price"] = df["latest_price"].apply(format_price)

            # Count how many stocks have valid prices (not N/A)
            prices_with_values = (display_df["Price"] != "N/A").sum()
            total_stocks = len(display_df)

            # Always show all stocks - show info about price collection status
            if prices_with_values == total_stocks:
                # All stocks have prices
                st.success(f"✅ All {total_stocks} stocks have price data!")
            elif prices_with_values > 0:
                # Some stocks have prices - show progress
                st.info(
                    f"📊 Showing all {total_stocks} stocks. {prices_with_values} stocks have prices ({100*prices_with_values//total_stocks}%). Prices are being collected for remaining stocks..."
                )
            elif total_stocks > 0:
                # No prices yet - start collection
                st.warning(
                    f"⚠️ Showing all {total_stocks} stocks, but no prices available yet. Starting price data collection..."
                )
                try:
                    track_response = requests.post(f"{API_URL}/api/track-popular", timeout=10)
                    if track_response.status_code == 200:
                        st.info(
                            "🔄 Started price data collection for all stocks - this may take a few minutes. Prices will appear as they are collected."
                        )
                except:
                    pass
        else:
            # Create Price column with N/A if latest_price column doesn't exist
            if len(df) > 0:
                display_df["Price"] = "N/A"
                st.warning(
                    f"⚠️ Price column not found in data. {len(df)} stocks loaded but 'latest_price' column is missing. This might be a data issue."
                )
                # Try to show sample data for debugging
                if len(df) > 0:
                    st.json({"sample_data": df.iloc[0].to_dict(), "columns": list(df.columns)})
            else:
                display_df["Price"] = "N/A"

        # Show mentions count - ALWAYS show (0 if no mentions)
        if "mention_count" in df.columns:
            display_df["Mentions"] = df["mention_count"].apply(lambda x: int(x) if pd.notna(x) and x is not None else 0)
        else:
            display_df["Mentions"] = 0

        # Show Status - ALWAYS show for all stocks (Twitter: X, Polygon: Y or "No mentions")
        if "twitter_mentions" in df.columns and "polygon_mentions" in df.columns:
            # Create status column showing source breakdown
            def get_status(row):
                twitter = int(row.get("twitter_mentions", 0) or 0)
                polygon = int(row.get("polygon_mentions", 0) or 0)
                total = int(row.get("mention_count", 0) or 0)

                if total > 0:
                    sources = []
                    if twitter > 0:
                        sources.append(f"Twitter: {twitter}")
                    if polygon > 0:
                        sources.append(f"Polygon: {polygon}")
                    return ", ".join(sources) if sources else "No mentions"
                else:
                    return "No mentions"

            display_df["Status"] = df.apply(get_status, axis=1)
        else:
            # Fallback: use mention_count if available
            if "mention_count" in df.columns:
                display_df["Status"] = df["mention_count"].apply(
                    lambda x: "Has mentions" if pd.notna(x) and int(x) > 0 else "No mentions"
                )
            else:
                display_df["Status"] = "No mentions"

        # Show Sentiment - ALWAYS show for all stocks (0.000 if not available)
        if "avg_sentiment" in df.columns:
            display_df["Sentiment"] = df["avg_sentiment"].apply(
                lambda x: f"{float(x):.3f}" if pd.notna(x) and x is not None and x != "" else "0.000"
            )
        else:
            display_df["Sentiment"] = "0.000"

        # Show 24h Change - ALWAYS show for all stocks (N/A if not available)
        if "price_change_24h" in df.columns:
            display_df["24h Change"] = df["price_change_24h"].apply(
                lambda x: f"{float(x):+.2f}%" if pd.notna(x) and x is not None and x != "" else "N/A"
            )
        else:
            display_df["24h Change"] = "N/A"

        # Select and order columns for display - ALWAYS show all columns: Price, Mentions, Status, Sentiment, 24h Change
        display_columns = ["ticker", "Price", "Mentions", "Status", "Sentiment", "24h Change"]

        # Ensure all columns exist (create missing ones with default values)
        for col in display_columns:
            if col not in display_df.columns:
                if col == "Sentiment":
                    display_df["Sentiment"] = "0.000"
                elif col == "24h Change":
                    display_df["24h Change"] = "N/A"
                elif col == "Status":
                    display_df["Status"] = "No mentions"

        # Select only the columns we want, in the order we want
        display_columns = [col for col in display_columns if col in display_df.columns]
        display_df = display_df[display_columns].copy()

        # Rename columns to ensure proper display names
        column_map = {
            "ticker": "Ticker",
            "Mentions": "Mentions",
            "Status": "Status",
            "Sentiment": "Sentiment",
            "Price": "Price",
            "24h Change": "24h Change",
        }
        display_df.columns = [column_map.get(col, col) for col in display_df.columns]

        # Display table - always show ALL stocks with their data
        st.subheader(f"All Stocks ({len(display_df)} stocks)")

        # Check data availability
        stocks_with_prices = (display_df["Price"] != "N/A").sum() if "Price" in display_df.columns else 0
        stocks_with_mentions_count = (display_df["Mentions"] > 0).sum() if "Mentions" in display_df.columns else 0

        # Show data status
        status_cols = st.columns(3)
        with status_cols[0]:
            if stocks_with_prices > 0:
                st.success(f"💰 {stocks_with_prices} stocks have prices")
            else:
                st.warning("💰 Fetching prices...")
        with status_cols[1]:
            if stocks_with_mentions_count > 0:
                st.success(f"📊 {stocks_with_mentions_count} stocks have mentions")
            else:
                st.info("📊 Collecting mentions...")
        with status_cols[2]:
            if stocks_with_mentions:
                st.success(f"✅ {len(stocks_with_mentions)} stocks with Twitter/Polygon data!")
            else:
                st.info("💡 Monitoring active - data appearing as collected")

        # Auto-trigger price fetching for stocks missing prices if needed
        if stocks_with_prices < len(display_df) * 0.5:  # If less than 50% have prices
            try:
                # Trigger price collection in background
                track_response = requests.post(f"{API_URL}/api/track-popular", timeout=5)
                if track_response.status_code == 200:
                    st.caption("🔄 Price collection in progress... Prices will appear as they are fetched.")
            except:
                pass

        # Show the table - ALL stocks are displayed with their data (prices, mentions, status, sentiment)
        try:
            st.dataframe(display_df, use_container_width=True, hide_index=True, height=600)

            # Show data summary
            st.caption(
                f"📊 Displaying all {len(display_df)} stocks with their data: {stocks_with_prices} with prices, {stocks_with_mentions_count} with mentions"
            )
        except Exception as e:
            st.error(f"Error displaying table: {e}")
            st.exception(e)

        # Visualizations (only if we have mentions)
        if stocks_with_mentions and len(df) > 0:
            st.markdown("---")
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("Top 20 by Mentions")
                top_mentions = df.nlargest(20, "mention_count") if "mention_count" in df.columns else df.head(20)
                if (
                    len(top_mentions) > 0
                    and "mention_count" in top_mentions.columns
                    and top_mentions["mention_count"].sum() > 0
                ):
                    fig = px.bar(
                        top_mentions,
                        x="ticker",
                        y="mention_count",
                        labels={"ticker": "Ticker", "mention_count": "Mentions"},
                        color="mention_count",
                        color_continuous_scale="Blues",
                    )
                    fig.update_xaxes(tickangle=45)
                    fig.update_layout(showlegend=False, height=400)
                    st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.subheader("Sentiment Distribution")
                if (
                    "avg_sentiment" in df.columns
                    and df["avg_sentiment"].notna().any()
                    and df["avg_sentiment"].abs().sum() > 0
                ):
                    fig = px.histogram(
                        df[df["avg_sentiment"].notna()],
                        x="avg_sentiment",
                        nbins=30,
                        labels={"avg_sentiment": "Average Sentiment", "count": "Number of Stocks"},
                        color_discrete_sequence=["#3b82f6"],
                    )
                    fig.update_layout(showlegend=False, height=400)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("💡 Mentions and sentiment charts will appear once Twitter/Reddit data is collected.")

    with tab2:
        st.header("Search Individual Stock")

        # Initialize session state for selected ticker
        if "selected_ticker" not in st.session_state:
            st.session_state.selected_ticker = ""

        # Get list of available tickers for dropdown (with timeout handling)
        try:
            trending = fetch_trending_tickers(hours=time_window, limit=5000)
            available_tickers = sorted([t["ticker"] for t in trending]) if trending else []
        except:
            # If API times out, use popular stocks as fallback
            available_tickers = []

        # Popular stocks - always show these first in dropdown
        popular_stocks = [
            "AAPL",
            "MSFT",
            "GOOGL",
            "AMZN",
            "NVDA",
            "META",
            "TSLA",
            "GME",
            "AMC",
            "SPY",
            "NFLX",
            "AMD",
            "INTC",
            "JPM",
            "BAC",
            "WMT",
            "TGT",
            "COST",
            "HD",
            "NKE",
        ]

        # Build options list: popular stocks first, then all others
        all_tickers_set = set(available_tickers)
        all_tickers_set.update(popular_stocks)
        all_other_tickers = sorted([t for t in all_tickers_set if t not in popular_stocks])

        # Options: popular stocks first, then all others (so they're always visible)
        options = popular_stocks + all_other_tickers

        # Format function to mark popular stocks (define before use)
        def format_ticker(ticker):
            if ticker in popular_stocks:
                return f"📈 {ticker}"
            return ticker

        # Check if a button was clicked in previous render and handle it
        # Use a separate session state key for button clicks
        if "button_selected_ticker" in st.session_state and st.session_state.button_selected_ticker:
            selected_from_button = st.session_state.button_selected_ticker
            st.session_state.selected_ticker = selected_from_button
            st.session_state.button_selected_ticker = None  # Clear it after use

        # Create the selectbox - this acts as both search and dropdown
        # Popular stocks are always shown first, then user can type to filter
        col1, col2 = st.columns([4, 1])
        with col1:
            # Find index of currently selected ticker
            selected_index = 0
            current_selection = st.session_state.get("selected_ticker", "")
            if current_selection and current_selection in options:
                try:
                    selected_index = options.index(current_selection)
                except ValueError:
                    selected_index = 0

            # Create the selectbox - Streamlit's selectbox is searchable
            # It acts as both a text input and dropdown, with popular stocks marked
            selected_ticker = st.selectbox(
                "🔍 Search or select a stock ticker (type to search)",
                options=options,
                index=selected_index,
                format_func=format_ticker,
                help="Type to search or scroll to find a stock. Popular stocks (marked with 📈) are shown first.",
                key="stock_search_selectbox",
            )

            # Update session state when selection changes (remove emoji prefix if present)
        if selected_ticker:
            # Remove emoji prefix if format_func added it (format_func only affects display, not value)
            clean_ticker = selected_ticker.replace("📈 ", "").strip()
            st.session_state.selected_ticker = clean_ticker

        with col2:
            st.write("")  # Spacing
            st.write("")  # Spacing
            if st.button("🔍 Search", use_container_width=True, key="search_button"):
                if st.session_state.selected_ticker:
                    st.rerun()

        # Show popular stock buttons AFTER selectbox
        # Clicking a button will set the ticker and trigger a rerun
        st.markdown("### Quick Access - Popular Stocks")
        st.caption(
            "💡 Click any button below to quickly select that stock. All popular stocks (marked with 📈) appear first in the dropdown above."
        )
        popular_stocks_display = [
            "AAPL",
            "MSFT",
            "GOOGL",
            "AMZN",
            "NVDA",
            "META",
            "TSLA",
            "GME",
            "AMC",
            "SPY",
            "NFLX",
            "AMD",
            "INTC",
            "JPM",
            "BAC",
            "WMT",
            "TGT",
            "COST",
            "HD",
            "NKE",
        ]
        cols = st.columns(10)
        for i, ticker in enumerate(popular_stocks_display):
            with cols[i % 10]:
                # Use on_click callback to set the ticker
                def make_callback(t):
                    def callback():
                        st.session_state.button_selected_ticker = t
                        st.session_state.selected_ticker = t

                    return callback

                st.button(ticker, key=f"popular_btn_{ticker}", use_container_width=True, on_click=make_callback(ticker))

        # Show data for selected ticker
        if st.session_state.selected_ticker:
            ticker = st.session_state.selected_ticker.upper().strip()

            # Validate ticker format (basic validation)
            if not ticker or len(ticker) > 5 or not ticker.isalpha():
                st.warning(
                    f"⚠️ Invalid ticker format: '{ticker}'. Please enter a valid stock ticker symbol (1-5 letters)."
                )
            else:
                # Trigger data collection for this ticker if needed
                try:
                    track_response = requests.post(f"{API_URL}/api/ticker/{ticker}/track", timeout=10)
                    if track_response.status_code == 200:
                        st.success(f"✅ Tracking {ticker} - fetching price and news data...")
                except:
                    pass  # Tracking might already be in progress

                # Fetch data - always fetch fresh data (TTL is short for freshness)
                with st.spinner(f"Loading data for {ticker}..."):
                    stats = fetch_ticker_stats(ticker, hours=time_window)
                    sentiment_trend = fetch_ticker_sentiment(ticker, hours=time_window)
                    price_history = fetch_ticker_price_history(ticker, days=7)

                # Always try to fetch real-time price if not in stats (with longer timeout)
                if not stats or not stats.get("latest_price"):
                    try:
                        # Try to fetch price directly from API
                        price_response = requests.get(f"{API_URL}/api/ticker/{ticker}/price", timeout=15)
                        if price_response.status_code == 200:
                            price_data = price_response.json()
                            if not stats:
                                stats = {}
                            if "price" in price_data:
                                stats["latest_price"] = price_data.get("price")
                                stats["current_price"] = price_data
                    except requests.exceptions.Timeout:
                        pass  # Price fetch timed out, continue with existing data
                    except Exception as e:
                        pass  # Price fetch is optional

                # Always show the data section - initialize stats if empty
                if not stats:
                    stats = {}

                # Ensure we have all required fields with defaults
                if "mention_count" not in stats:
                    stats["mention_count"] = 0
                if "twitter_mentions" not in stats:
                    stats["twitter_mentions"] = 0
                if "polygon_mentions" not in stats:
                    stats["polygon_mentions"] = 0
                if "avg_sentiment" not in stats:
                    stats["avg_sentiment"] = 0.0

                # Key metrics - always show data from API/database
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    # Get price from multiple sources
                    price = stats.get("latest_price")
                    if price is None:
                        current_price_data = stats.get("current_price")
                        if current_price_data:
                            if isinstance(current_price_data, dict):
                                price = current_price_data.get("price")
                            elif isinstance(current_price_data, (int, float)):
                                price = current_price_data

                    # Display price
                    if price is not None and isinstance(price, (int, float)) and price > 0:
                        st.metric("Current Price", f"${price:.2f}")
                    else:
                        st.metric("Current Price", "N/A")
                        # Try to fetch price if not available (with longer timeout)
                        try:
                            price_response = requests.get(f"{API_URL}/api/ticker/{ticker}/price", timeout=15)
                            if price_response.status_code == 200:
                                price_data = price_response.json()
                                if price_data.get("price"):
                                    st.info(f"💰 Fetching price... ${price_data['price']:.2f}")
                        except requests.exceptions.Timeout:
                            st.info(f"⏳ Price fetch taking longer than expected for {ticker}...")
                        except:
                            pass

                with col2:
                    mention_count = stats.get("mention_count", 0)
                    twitter_mentions = stats.get("twitter_mentions", 0)
                    polygon_mentions = stats.get("polygon_mentions", 0)

                    # Show total mentions with breakdown
                    st.metric("Total Mentions", mention_count)
                    if mention_count > 0:
                        st.caption(f"🐦 Twitter: {twitter_mentions} | 📰 Polygon: {polygon_mentions}")
                    else:
                        st.caption("📊 Collecting mentions from Twitter and Polygon...")
                        # Show info about data collection
                        if twitter_mentions == 0 and polygon_mentions == 0:
                            st.info("💡 Mentions will appear as they are collected from Twitter and Polygon news.")

                with col3:
                    avg_sentiment = stats.get("avg_sentiment", 0.0)
                    st.metric("Avg Sentiment", f"{avg_sentiment:.3f}")
                    if avg_sentiment > 0.1:
                        st.caption("🟢 Positive")
                    elif avg_sentiment < -0.1:
                        st.caption("🔴 Negative")
                    else:
                        st.caption("⚪ Neutral")

                with col4:
                    change_pct = stats.get("price_change_percent_24h")
                    if change_pct is None:
                        price_change = stats.get("price_change", {})
                        if price_change:
                            change_pct = price_change.get("change_percent", 0)

                    if change_pct is not None:
                        st.metric("24h Change", f"{change_pct:+.2f}%")
                    else:
                        st.metric("24h Change", "N/A")

                # Sentiment trend - always show chart with real data
                st.subheader("📈 Sentiment Trend Over Time")
                if sentiment_trend and len(sentiment_trend) > 0:
                    df_sentiment = pd.DataFrame(sentiment_trend)
                    df_sentiment["hour"] = pd.to_datetime(df_sentiment["hour"])

                    # Ensure avg_sentiment column exists and is numeric
                    if "avg_sentiment" in df_sentiment.columns:
                        df_sentiment["avg_sentiment"] = pd.to_numeric(
                            df_sentiment["avg_sentiment"], errors="coerce"
                        ).fillna(0.0)
                    else:
                        df_sentiment["avg_sentiment"] = 0.0

                    fig = go.Figure()
                    fig.add_trace(
                        go.Scatter(
                            x=df_sentiment["hour"],
                            y=df_sentiment["avg_sentiment"],
                            mode="lines+markers",
                            name="Sentiment",
                            line=dict(color="blue", width=2),
                            fill="tozeroy",
                            fillcolor="rgba(59, 130, 246, 0.1)",
                            hovertemplate="Time: %{x}<br>Sentiment: %{y:.3f}<extra></extra>",
                        )
                    )
                    fig.add_hline(y=0, line_dash="dash", line_color="gray", annotation_text="Neutral")
                    fig.update_layout(
                        title=f"Sentiment Trend for {ticker} (from Twitter & Polygon)",
                        xaxis_title="Time",
                        yaxis_title="Sentiment Score",
                        hovermode="x unified",
                        height=400,
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    # Show summary stats
                    if len(df_sentiment) > 0:
                        avg_sent = df_sentiment["avg_sentiment"].mean()
                        max_sent = df_sentiment["avg_sentiment"].max()
                        min_sent = df_sentiment["avg_sentiment"].min()
                        st.caption(f"📊 Average: {avg_sent:.3f} | Max: {max_sent:.3f} | Min: {min_sent:.3f}")
                else:
                    st.info(
                        f"📊 No sentiment data available yet for {ticker}. Sentiment will appear as mentions are collected from Twitter and Polygon."
                    )
                    # Show empty chart placeholder
                    fig = go.Figure()
                    fig.add_annotation(
                        x=0.5,
                        y=0.5,
                        xref="paper",
                        yref="paper",
                        text="No sentiment data available yet<br>Data will appear as mentions are collected",
                        showarrow=False,
                        font=dict(size=16, color="gray"),
                    )
                    fig.update_layout(
                        title=f"Sentiment Trend for {ticker}",
                        xaxis_title="Time",
                        yaxis_title="Sentiment Score",
                        height=400,
                    )
                    st.plotly_chart(fig, use_container_width=True)

                # Mention volume over time - always show chart with real data from Twitter and Polygon
                st.subheader("📊 Mention Volume Over Time (Twitter & Polygon)")
                if sentiment_trend and len(sentiment_trend) > 0:
                    df_sentiment = pd.DataFrame(sentiment_trend)
                    df_sentiment["hour"] = pd.to_datetime(df_sentiment["hour"])

                    # Ensure Twitter and Polygon columns exist with default values
                    if "twitter_mentions" not in df_sentiment.columns:
                        df_sentiment["twitter_mentions"] = 0
                    if "polygon_mentions" not in df_sentiment.columns:
                        df_sentiment["polygon_mentions"] = 0
                    if "mention_count" not in df_sentiment.columns:
                        df_sentiment["mention_count"] = (
                            df_sentiment["twitter_mentions"] + df_sentiment["polygon_mentions"]
                        )

                    # Fill NaN values with 0 and convert to int
                    df_sentiment["twitter_mentions"] = (
                        pd.to_numeric(df_sentiment["twitter_mentions"], errors="coerce").fillna(0).astype(int)
                    )
                    df_sentiment["polygon_mentions"] = (
                        pd.to_numeric(df_sentiment["polygon_mentions"], errors="coerce").fillna(0).astype(int)
                    )
                    df_sentiment["mention_count"] = (
                        pd.to_numeric(df_sentiment["mention_count"], errors="coerce").fillna(0).astype(int)
                    )

                    # Create stacked bar chart showing Twitter and Polygon mentions separately
                    fig2 = go.Figure()
                    fig2.add_trace(
                        go.Bar(
                            x=df_sentiment["hour"],
                            y=df_sentiment["twitter_mentions"],
                            name="🐦 Twitter",
                            marker_color="#1DA1F2",
                            hovertemplate="<b>Twitter</b><br>Time: %{x}<br>Mentions: %{y}<extra></extra>",
                        )
                    )
                    fig2.add_trace(
                        go.Bar(
                            x=df_sentiment["hour"],
                            y=df_sentiment["polygon_mentions"],
                            name="📰 Polygon News",
                            marker_color="#3b82f6",
                            hovertemplate="<b>Polygon News</b><br>Time: %{x}<br>Mentions: %{y}<extra></extra>",
                        )
                    )
                    fig2.update_layout(
                        title=f"Mention Volume Over Time for {ticker} (from Twitter & Polygon)",
                        xaxis_title="Time",
                        yaxis_title="Number of Mentions",
                        barmode="stack",
                        height=400,
                        hovermode="x unified",
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    )
                    st.plotly_chart(fig2, use_container_width=True)

                    # Show summary stats
                    total_twitter = df_sentiment["twitter_mentions"].sum()
                    total_polygon = df_sentiment["polygon_mentions"].sum()
                    total_mentions = df_sentiment["mention_count"].sum()
                    st.caption(
                        f"📊 Total: {total_mentions} mentions | 🐦 Twitter: {total_twitter} | 📰 Polygon: {total_polygon}"
                    )
                else:
                    st.info(
                        f"📊 No mention data available yet for {ticker}. Mentions will appear as they are collected from Twitter and Polygon."
                    )
                    # Show empty chart placeholder
                    fig2 = go.Figure()
                    fig2.add_annotation(
                        x=0.5,
                        y=0.5,
                        xref="paper",
                        yref="paper",
                        text="No mention data available yet<br>Mentions will appear as they are collected<br>from Twitter and Polygon",
                        showarrow=False,
                        font=dict(size=16, color="gray"),
                    )
                    fig2.update_layout(
                        title=f"Mention Volume Over Time for {ticker}",
                        xaxis_title="Time",
                        yaxis_title="Number of Mentions",
                        height=400,
                    )
                    st.plotly_chart(fig2, use_container_width=True)

                # Price history - always show with real data from Polygon/Massive
                st.subheader("💰 Price History (Last 7 Days)")
                if price_history and len(price_history) > 0:
                    df_price = pd.DataFrame(price_history)
                    df_price["date"] = pd.to_datetime(df_price["date"])

                    # Ensure all required columns exist and are numeric
                    for col in ["open", "high", "low", "close", "volume"]:
                        if col in df_price.columns:
                            df_price[col] = pd.to_numeric(df_price[col], errors="coerce")

                    # Create candlestick chart
                    fig = go.Figure()
                    fig.add_trace(
                        go.Candlestick(
                            x=df_price["date"],
                            open=df_price["open"],
                            high=df_price["high"],
                            low=df_price["low"],
                            close=df_price["close"],
                            name=ticker,
                            increasing_line_color="#26a69a",
                            decreasing_line_color="#ef5350",
                        )
                    )
                    fig.update_layout(
                        title=f"Price History for {ticker} (from Polygon/Massive)",
                        xaxis_title="Date",
                        yaxis_title="Price ($)",
                        xaxis_rangeslider_visible=False,
                        height=400,
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    # Show price summary
                    if "close" in df_price.columns and len(df_price) > 0:
                        latest_price = df_price["close"].iloc[-1]
                        first_price = df_price["close"].iloc[0]
                        price_change = latest_price - first_price
                        price_change_pct = (price_change / first_price * 100) if first_price > 0 else 0
                        st.caption(
                            f"📊 Latest: ${latest_price:.2f} | 7d Change: ${price_change:+.2f} ({price_change_pct:+.2f}%)"
                        )
                else:
                    st.info(
                        f"💰 No price history available yet for {ticker}. Price data will appear as it is collected from Polygon/Massive."
                    )
                    # Show empty chart placeholder
                    fig = go.Figure()
                    fig.add_annotation(
                        x=0.5,
                        y=0.5,
                        xref="paper",
                        yref="paper",
                        text="No price history available yet<br>Price data will appear as it is collected",
                        showarrow=False,
                        font=dict(size=16, color="gray"),
                    )
                    fig.update_layout(
                        title=f"Price History for {ticker}", xaxis_title="Date", yaxis_title="Price ($)", height=400
                    )
                    st.plotly_chart(fig, use_container_width=True)

                # Additional info section - always show data sources
                st.markdown("---")
                st.subheader("📊 Data Sources & Summary")
                col1, col2 = st.columns(2)
                with col1:
                    st.write("**🐦 Twitter Mentions:**", stats.get("twitter_mentions", 0))
                    st.write("**📰 Polygon News Mentions:**", stats.get("polygon_mentions", 0))
                with col2:
                    st.write("**📈 Total Mentions:**", stats.get("mention_count", 0))
                    st.write("**💭 Average Sentiment:**", f"{stats.get('avg_sentiment', 0.0):.3f}")

                # Show data collection status
                if (
                    stats.get("mention_count", 0) == 0
                    and stats.get("twitter_mentions", 0) == 0
                    and stats.get("polygon_mentions", 0) == 0
                ):
                    st.info(
                        "💡 **Data Collection Status:** Mentions are being collected from Twitter and Polygon. They will appear here as they are found."
                    )
                else:
                    st.success(
                        f"✅ **Data Collection Active:** {stats.get('mention_count', 0)} mentions collected from Twitter and Polygon."
                    )


if __name__ == "__main__":
    main()
