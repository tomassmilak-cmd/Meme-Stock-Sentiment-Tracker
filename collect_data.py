#!/usr/bin/env python3
"""Simple script to start data collection for the dashboard."""
import requests
import time
import sys

API_URL = "http://127.0.0.1:8000"

def check_api():
    """Check if API is running."""
    try:
        response = requests.get(f"{API_URL}/health", timeout=3)
        if response.status_code == 200:
            return True
    except:
        pass
    return False

def start_collection():
    """Start data collection."""
    print("🚀 Starting data collection...")
    
    # Check API
    if not check_api():
        print("❌ API server is not running!")
        print("   Please start it with: python3 -m uvicorn api.main:app --host 127.0.0.1 --port 8000")
        return False
    
    print("✓ API server is running")
    
    # Start monitoring
    print("\n📡 Starting monitoring...")
    try:
        response = requests.post(f"{API_URL}/api/monitor/start", timeout=10)
        if response.status_code == 200:
            print(f"  ✓ {response.json().get('message', 'Monitoring started')}")
        else:
            print(f"  ⚠️  Status: {response.status_code}")
    except Exception as e:
        print(f"  ⚠️  Error: {e}")
    
    # Track popular stocks
    print("\n📈 Tracking popular stocks...")
    try:
        response = requests.post(f"{API_URL}/api/track-popular", timeout=60)
        if response.status_code == 200:
            data = response.json()
            print(f"  ✓ {data.get('message', 'Tracking started')}")
            if data.get('tracked'):
                print(f"  ✓ Tracked {len(data['tracked'])} tickers: {', '.join(data['tracked'][:10])}")
        else:
            print(f"  ⚠️  Status: {response.status_code}")
    except Exception as e:
        print(f"  ⚠️  Error: {e}")
    
    # Wait and check data
    print("\n⏳ Waiting for data to be collected...")
    time.sleep(5)
    
    print("\n📊 Checking collected data...")
    try:
        response = requests.get(f"{API_URL}/api/trending?limit=10", timeout=10)
        if response.status_code == 200:
            data = response.json()
            tickers = data.get('tickers', [])
            if tickers:
                print(f"  ✓ Found {len(tickers)} tracked tickers:")
                for t in tickers[:5]:
                    price = t.get('latest_price', 'N/A')
                    mentions = t.get('mention_count', 0)
                    print(f"    • {t['ticker']}: ${price} ({mentions} mentions)")
            else:
                print("  ⚠️  No tickers found yet. Data may still be collecting...")
        else:
            print(f"  ⚠️  Status: {response.status_code}")
    except Exception as e:
        print(f"  ⚠️  Error: {e}")
    
    print("\n✅ Data collection started!")
    print("   Open http://localhost:8501 to view the dashboard")
    print("   Click '🔄 Refresh Now' in the dashboard to see updated data")
    
    return True

if __name__ == "__main__":
    success = start_collection()
    sys.exit(0 if success else 1)

