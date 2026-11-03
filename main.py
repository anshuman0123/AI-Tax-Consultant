"""
AI Tax Consultant - Application Runner
Provides direct compatibility with 'uvicorn main:app' and 'python main.py'.
"""
import uvicorn
from backend.main import app
from backend.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=(settings.ENVIRONMENT == "development")
    )
