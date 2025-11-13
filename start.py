#!/usr/bin/env python3
"""Startup script for Meme Stock Sentiment Tracker"""
import subprocess
import time
import requests
import sys
import os

def check_service(url, name):
    """Check if a service is running"""
    try:
        response = requests.get(url, timeout=2)
        return response.status_code == 200
    except:
        return False

def start_api():
    """Start API server"""
    if check_service("http://localhost:8000/health", "API"):
        print("✓ API server is already running")
        return True
    
    print("→ Starting API server...")
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    process = subprocess.Popen(
        ["python3", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
        stdout=open("/tmp/meme_stock_api.log", "w"),
        stderr=subprocess.STDOUT
    )
    print(f"  API server started (PID: {process.pid})")
    return False

def start_dashboard():
    """Start Dashboard"""
    if check_service("http://localhost:8501", "Dashboard"):
        print("✓ Dashboard is already running")
        return True
    
    print("→ Starting Dashboard...")
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    env = os.environ.copy()
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    process = subprocess.Popen(
        ["python3", "-m", "streamlit", "run", "dashboard/app.py", 
         "--server.port", "8501", "--server.address", "0.0.0.0", "--server.headless=true"],
        stdout=open("/tmp/meme_stock_dashboard.log", "w"),
        stderr=subprocess.STDOUT,
        env=env
    )
    print(f"  Dashboard started (PID: {process.pid})")
    return False

def wait_for_api(max_wait=30):
    """Wait for API to be ready"""
    print("\n⏳ Waiting for API to be ready...")
    for i in range(max_wait):
        if check_service("http://localhost:8000/health", "API"):
            print("✓ API server is ready")
            return True
        time.sleep(1)
    print("⚠ API server not responding (may still be starting)")
    return False

def start_monitoring():
    """Start data collection"""
    print("\n→ Starting data collection...")
    try:
        response = requests.post("http://localhost:8000/api/monitor/start", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✓ {data.get('message', 'Monitoring started')}")
            return True
    except Exception as e:
        print(f"  Warning: Could not start monitoring: {e}")
    return False

def track_stocks():
    """Track popular stocks"""
    print("→ Tracking popular meme stocks...")
    try:
        response = requests.post("http://localhost:8000/api/track-popular", timeout=30)
        if response.status_code == 200:
            data = response.json()
            message = data.get('message', 'Unknown')
            print(f"✓ {message}")
            if 'tracked' in data and data['tracked']:
                print(f"  Tracked: {', '.join(data['tracked'][:5])}")
            return True
    except Exception as e:
        print(f"  Warning: Could not track stocks: {e}")
    return False

def main():
    print("🚀 Starting Meme Stock Sentiment Tracker...\n")
    
    api_running = start_api()
    dashboard_running = start_dashboard()
    
    if not api_running or not dashboard_running:
        time.sleep(3)
    
    wait_for_api()
    
    # Start monitoring and tracking
    start_monitoring()
    time.sleep(2)
    track_stocks()
    
    print("\n" + "="*50)
    print("✅ Meme Stock Sentiment Tracker is running!")
    print("\n📍 Access Points:")
    print("   Dashboard: http://localhost:8501")
    print("   API:       http://localhost:8000")
    print("   API Docs:  http://localhost:8000/docs")
    print("\n💡 Data collection is now active!")
    print("   - Twitter mentions are being collected")
    print("   - Stock prices are being tracked")
    print("   - Check the dashboard in a few minutes to see data")
    print("\n📝 Logs:")
    print("   API:      /tmp/meme_stock_api.log")
    print("   Dashboard: /tmp/meme_stock_dashboard.log")

if __name__ == "__main__":
    main()

