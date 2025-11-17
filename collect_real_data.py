#!/usr/bin/env python3
"""Script to collect real data for mentions and price changes."""
import requests
import time
import sys

API_URL = "http://127.0.0.1:8000"

def main():
    print("🚀 Collecting real data for the dashboard...")
    
    # Start monitoring
    try:
        r = requests.post(f"{API_URL}/api/monitor/start", timeout=5)
        print("✅ Monitoring started")
    except:
        print("⚠️  Monitoring may already be running")
    
    # Track popular stocks (gets prices)
    try:
        r = requests.post(f"{API_URL}/api/track-popular", timeout=30)
        print("✅ Stock prices tracked")
    except Exception as e:
        print(f"⚠️  Stock tracking: {e}")
    
    print("\n⏳ Waiting for Twitter/Reddit data collection...")
    print("   This may take 1-2 minutes as we search for mentions...")
    time.sleep(60)  # Wait for monitoring to collect data
    
    # Check results
    try:
        r = requests.get(f"{API_URL}/api/trending?limit=10", timeout=10)
        if r.status_code == 200:
            data = r.json()
            tickers = data.get('tickers', [])
            print(f"\n📊 Results:")
            print(f"   Found {len(tickers)} tickers with data")
            
            has_mentions = any(t.get('mention_count', 0) > 0 for t in tickers)
            if has_mentions:
                print("   ✅ Found mentions from Twitter/Reddit!")
            else:
                print("   ⚠️  No mentions yet (Twitter/Reddit may need more time)")
            
            for t in tickers[:6]:
                print(f"   {t['ticker']}: ${t.get('latest_price', 'N/A'):.2f if t.get('latest_price') else 'N/A'}")
    except Exception as e:
        print(f"Error checking data: {e}")
    
    print("\n✅ Data collection complete!")
    print("   Refresh your dashboard to see the updated values")

if __name__ == "__main__":
    main()

