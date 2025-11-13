"""Main entry point for the application."""
import uvicorn
from config import settings

if __name__ == "__main__":
    print("Starting Meme Stock Sentiment Tracker...")
    print(f"API will be available at http://{settings.api_host}:{settings.api_port}")
    print(f"Dashboard will be available at http://localhost:8501")
    print("\nTo start the services:")
    print("1. Start API: uvicorn api.main:app --reload")
    print("2. Start Dashboard: streamlit run dashboard/app.py")
    print("3. Or use Docker: docker-compose up")
    
    # Start API server
    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True
    )

