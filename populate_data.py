#!/usr/bin/env python3
"""Quick script to populate initial data for the dashboard."""
import requests
import time
import sys

API_URL = "http://127.0.0.1:8000"

def populate_data():
    """Populate initial stock data."""
    print("📊 Populating initial data...")
    
    # Check API
    try:
        r = requests.get(f"{API_URL}/health", timeout=2)
        if r.status_code != 200:
            print("❌ API not responding")
            return False
    except:
        print("❌ API not running. Start it with: python3 -m uvicorn api.main:app --host 127.0.0.1 --port 8000")
        return False
    
    # Start tracking popular stocks
    print("📈 Tracking popular stocks...")
    try:
        r = requests.post(f"{API_URL}/api/track-popular", timeout=15)
        if r.status_code == 200:
            data = r.json()
            print(f"✅ {data.get('message', 'Started tracking')}")
        else:
            print(f"⚠️  Status: {r.status_code}")
    except Exception as e:
        print(f"⚠️  Error: {e}")
    
    # Wait a moment for data to be collected
    print("⏳ Waiting for data collection...")
    time.sleep(3)
    
    # Check if we have data
    try:
        r = requests.get(f"{API_URL}/api/trending?limit=10", timeout=5)
        if r.status_code == 200:
            data = r.json()
            tickers = data.get('tickers', [])
            if tickers:
                print(f"✅ Found {len(tickers)} tickers with data:")
                for t in tickers[:5]:
                    price = t.get('latest_price', 'N/A')
                    print(f"   • {t['ticker']}: ${price}")
                return True
            else:
                print("⚠️  No tickers found yet. Data may still be collecting...")
                return False
    except Exception as e:
        print(f"⚠️  Error checking data: {e}")
        return False

if __name__ == "__main__":
    success = populate_data()
    if success:
        print("\n✅ Data populated! Refresh your dashboard at http://localhost:8501")
    else:
        print("\n⚠️  Some data may still be loading. Try refreshing the dashboard in a few seconds.")
    sys.exit(0 if success else 1)

