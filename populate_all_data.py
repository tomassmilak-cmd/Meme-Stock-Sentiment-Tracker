#!/usr/bin/env python3
"""Script to populate all data: prices, historical prices, news, and Twitter mentions."""
import requests
import time
import sys

API_URL = "http://127.0.0.1:8000"

def main():
    print("🚀 Populating all data sources...")
    print("   This will collect: Prices, Historical Prices, News Sentiment, Twitter Mentions\n")
    
    # Check API
    try:
        r = requests.get(f"{API_URL}/health", timeout=3)
        if r.status_code != 200:
            print("❌ API not responding")
            return False
    except:
        print("❌ API not running. Start it with: ./start_all.sh")
        return False
    
    # 1. Start monitoring (Twitter/Reddit)
    print("1️⃣ Starting social media monitoring...")
    try:
        r = requests.post(f"{API_URL}/api/monitor/start", timeout=5)
        if r.status_code == 200:
            print("   ✅ Monitoring started")
    except:
        print("   ⚠️  Monitor may already be running")
    
    # 2. Track popular stocks (prices + historical + news)
    print("\n2️⃣ Tracking stocks with prices, historical data, and news...")
    try:
        r = requests.post(f"{API_URL}/api/track-popular", timeout=15)
        if r.status_code == 200:
            data = r.json()
            print(f"   ✅ {data.get('message', 'Tracking started')}")
            if data.get('tracked'):
                print(f"   📊 Tracking {len(data['tracked'])} tickers")
    except Exception as e:
        print(f"   ⚠️  Error: {e}")
    
    # 3. Wait for background data collection
    print("\n3️⃣ Waiting for data collection (news, historical prices, Twitter)...")
    print("   This may take 30-60 seconds...")
    
    for i in range(6):
        time.sleep(10)
        print(f"   ⏳ {i+1}/6 - Checking progress...")
        
        try:
            r = requests.get(f"{API_URL}/api/trending?limit=6", timeout=5)
            if r.status_code == 200:
                data = r.json()
                tickers = data.get('tickers', [])
                
                # Check if we have any data
                total_mentions = sum(t.get('mention_count', 0) for t in tickers)
                has_price_changes = any(t.get('price_change_24h') is not None for t in tickers)
                
                if total_mentions > 0 or has_price_changes:
                    print(f"   ✅ Found data! {total_mentions} total mentions, {sum(1 for t in tickers if t.get('price_change_24h') is not None)} tickers with price changes")
                    break
        except:
            pass
    
    # 4. Final check
    print("\n4️⃣ Final data check...")
    try:
        r = requests.get(f"{API_URL}/api/trending?limit=6", timeout=5)
        if r.status_code == 200:
            data = r.json()
            tickers = data.get('tickers', [])
            
            print(f"\n📊 Results:")
            print(f"   Found {len(tickers)} tickers")
            
            total_mentions = 0
            total_sentiment = 0.0
            price_changes = 0
            
            for t in tickers:
                mentions = t.get('mention_count', 0)
                sentiment = t.get('avg_sentiment', 0.0)
                price = t.get('latest_price', 'N/A')
                change = t.get('price_change_24h')
                
                total_mentions += mentions
                if sentiment != 0:
                    total_sentiment += sentiment
                if change is not None:
                    price_changes += 1
                
                change_str = f"{change:+.2f}%" if change is not None else "N/A"
                print(f"   {t['ticker']}: ${price:.2f if isinstance(price, (int, float)) else price}")
                print(f"      Mentions: {mentions}, Sentiment: {sentiment:.3f}, Change: {change_str}")
            
            print(f"\n✅ Summary:")
            print(f"   Total Mentions: {total_mentions}")
            print(f"   Average Sentiment: {total_sentiment/len(tickers):.3f}" if len(tickers) > 0 else "   Average Sentiment: 0.000")
            print(f"   Tickers with Price Changes: {price_changes}/{len(tickers)}")
            
            if total_mentions == 0:
                print("\n💡 Note: Mentions are still 0. This means:")
                print("   - Twitter/Reddit monitoring needs more time to collect data")
                print("   - Or Polygon news endpoint may not be available on your plan")
                print("   - Monitoring is running in background - check back in a few minutes")
            
            if price_changes == 0:
                print("\n💡 Note: Price changes are N/A. Historical data may still be collecting.")
                print("   - This is normal - historical prices are being fetched in background")
            
            return True
    except Exception as e:
        print(f"   Error: {e}")
        return False
    
    print("\n✅ Data population complete!")
    print("   Refresh your dashboard at http://localhost:8501 to see the data")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

