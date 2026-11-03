import os
from typing import List
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Settings(BaseModel):
    """
    Application Settings loaded from environment variables or .env file.
    Default placeholder values are provided for safe repository commits.
    """
    # Server Configuration
    HOST: str = Field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    PORT: int = Field(default_factory=lambda: int(os.getenv("PORT", "8001")))
    ENVIRONMENT: str = Field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    ALLOWED_ORIGINS: str = Field(
        default_factory=lambda: os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:8001,https://localhost,http://localhost:5500,http://127.0.0.1:8001"
        )
    )

    # Google Gemini AI
    GEMINI_API_KEY: str = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    GEMINI_MODEL: str = Field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))

    # Pinecone Vector Store
    PINECONE_API_KEY: str = Field(default_factory=lambda: os.getenv("PINECONE_API_KEY", ""))
    PINECONE_INDEX_HOST: str = Field(default_factory=lambda: os.getenv("PINECONE_INDEX_HOST", ""))
    PINECONE_NAMESPACE: str = Field(default_factory=lambda: os.getenv("PINECONE_NAMESPACE", "income_tax_act_1961"))
    PINECONE_TOP_K: int = Field(default_factory=lambda: int(os.getenv("PINECONE_TOP_K", "4")))

    # Authentication & Security
    GOOGLE_CLIENT_ID: str = Field(
        default_factory=lambda: os.getenv(
            "GOOGLE_CLIENT_ID",
            "your_google_oauth_client_id.apps.googleusercontent.com"
        )
    )
    JWT_SECRET_KEY: str = Field(
        default_factory=lambda: os.getenv(
            "JWT_SECRET_KEY",
            "your_secure_random_jwt_secret_key_change_in_production"
        )
    )
    JWT_ALGORITHM: str = Field(default_factory=lambda: os.getenv("JWT_ALGORITHM", "HS256"))
    JWT_EXPIRATION_DAYS: int = Field(default_factory=lambda: int(os.getenv("JWT_EXPIRATION_DAYS", "30")))

    # MongoDB
    MONGODB_URI: str = Field(default_factory=lambda: os.getenv("MONGODB_URI", "mongodb://localhost:27017/"))
    MONGODB_DB_NAME: str = Field(default_factory=lambda: os.getenv("MONGODB_DB_NAME", "taxassist_user"))

    # Dodo Payments
    DODO_PAYMENTS_API_KEY: str = Field(default_factory=lambda: os.getenv("DODO_PAYMENTS_API_KEY", ""))
    DODO_PAYMENTS_ENVIRONMENT: str = Field(default_factory=lambda: os.getenv("DODO_PAYMENTS_ENVIRONMENT", "test_mode"))
    DODO_PRODUCT_ID: str = Field(default_factory=lambda: os.getenv("DODO_PRODUCT_ID", "your_product_id_here"))
    DODO_RETURN_URL: str = Field(default_factory=lambda: os.getenv("DODO_RETURN_URL", "http://localhost:8001/api/payment_status"))

    # Optional Supplementary Documents
    SUPPLEMENTARY_PDF_PATH: str = Field(default_factory=lambda: os.getenv("SUPPLEMENTARY_PDF_PATH", ""))

    @property
    def cors_origins(self) -> List[str]:
        """Parse comma-separated origins string into a list."""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]


settings = Settings()
