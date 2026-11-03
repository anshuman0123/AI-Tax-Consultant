import logging
from typing import Optional, Any
from backend.config import settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages MongoDB connection pool and collection access."""

    def __init__(self):
        self._client: Optional[Any] = None
        self._db: Optional[Any] = None

    def get_client(self):
        """Initializes and returns the singleton MongoClient."""
        if self._client is None:
            try:
                from pymongo import MongoClient
                self._client = MongoClient(
                    settings.MONGODB_URI,
                    serverSelectionTimeoutMS=3000
                )
                logger.info("MongoDB client initialized successfully.")
            except ImportError:
                logger.warning("pymongo is not installed. Database persistence will be disabled.")
                return None
            except Exception as e:
                logger.error(f"Failed to initialize MongoDB client: {e}")
                return None
        return self._client

    def get_database(self):
        """Returns the application database instance."""
        if self._db is None:
            client = self.get_client()
            if client is not None:
                self._db = client[settings.MONGODB_DB_NAME]
        return self._db

    def get_user_collection(self):
        """Returns the user details collection."""
        db = self.get_database()
        if db is not None:
            return db["userdetails"]
        return None

    def close(self):
        """Closes the MongoDB connection."""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
            self._db = None
            logger.info("MongoDB connection closed.")


db_manager = DatabaseManager()


def get_user_collection():
    """Dependency helper to get user details collection."""
    return db_manager.get_user_collection()
