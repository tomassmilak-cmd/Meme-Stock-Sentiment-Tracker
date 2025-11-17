@st.cache_data(ttl=30)
def fetch_ticker_stats(ticker: str, hours: int = 24) -> Dict:
    """Fetch stats for a specific ticker."""
    try:
        response = requests.get(
            f"{API_URL}/api/ticker/{ticker}/stats",
            params={"hours": hours},
            timeout=5
        )
        if response.status_code == 200:
            return response.json()
        else:
            return {}
    except Exception as e:
        return {}

