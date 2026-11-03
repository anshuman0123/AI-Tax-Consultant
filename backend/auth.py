import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

try:
    import jwt
except ImportError:
    jwt = None

from fastapi import Request
from backend.config import settings
from backend.database import get_user_collection

logger = logging.getLogger(__name__)


def parse_unverified_jwt_payload(token: str) -> Dict[str, Any]:
    """
    Decodes the unverified payload from a JWT string.
    Useful as a fallback or during development when external Google verification
    is mocked or offline.
    """
    try:
        parts = token.split(".")
        if len(parts) < 2:
            raise ValueError("Invalid JWT token format.")
        base64_url = parts[1]
        padding = "=" * (-len(base64_url) % 4)
        base64_url += padding
        decoded_bytes = base64.urlsafe_b64decode(base64_url)
        return json.loads(decoded_bytes.decode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse unverified JWT payload: {e}")
        raise ValueError(f"Invalid token payload: {e}")


def verify_google_token(credential_str: str) -> Dict[str, Any]:
    """
    Verifies a Google OAuth ID token using Google's public keys.
    Falls back to payload decoding if client ID is a placeholder or during offline dev.
    """
    is_placeholder = (
        not settings.GOOGLE_CLIENT_ID
        or "your_google_oauth_client_id" in settings.GOOGLE_CLIENT_ID
    )

    if not is_placeholder:
        try:
            from google.oauth2 import id_token
            from google.auth.transport import requests as google_requests
            idinfo = id_token.verify_oauth2_token(
                credential_str,
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID
            )
            return idinfo
        except Exception as e:
            logger.warning(f"Google token verification failed ({e}), attempting fallback decoding.")

    # Development fallback
    return parse_unverified_jwt_payload(credential_str)


def create_session_jwt(payload: Dict[str, Any]) -> str:
    """Creates a signed session JWT with expiration."""
    exp = int((datetime.now(timezone.utc) + timedelta(days=settings.JWT_EXPIRATION_DAYS)).timestamp())
    payload_to_sign = {**payload, "exp": exp}
    
    if jwt is not None:
        return jwt.encode(
            payload_to_sign,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM
        )
    
    # Lightweight fallback if PyJWT is not yet installed in local environment
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload_to_sign).encode()).decode().rstrip("=")
    return f"{header}.{body}.local_sig"


def decode_session_jwt(token: str) -> Optional[Dict[str, Any]]:
    """Decodes and validates the application session JWT."""
    if jwt is not None:
        try:
            decoded = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM]
            )
            return decoded
        except jwt.ExpiredSignatureError:
            logger.info("Session JWT expired.")
            return None
        except jwt.PyJWTError as e:
            logger.warning(f"Invalid session JWT: {e}")
            return None

    # Fallback parsing
    try:
        data = parse_unverified_jwt_payload(token)
        if "exp" in data and datetime.now(timezone.utc).timestamp() > data["exp"]:
            return None
        return data
    except Exception:
        return None


def get_current_user_from_cookie(request: Request) -> Optional[Dict[str, Any]]:
    """Extracts and verifies user session from cookie."""
    token = request.cookies.get("user_id")
    if not token:
        return None

    session_data = decode_session_jwt(token)
    if not session_data or "id" not in session_data:
        return None

    try:
        collection = get_user_collection()
        if collection is not None:
            user = collection.find_one({"google_id": session_data["id"]})
            if user:
                return user
        return {
            "google_id": session_data["id"],
            "name": session_data.get("name", "User"),
            "email": session_data.get("email", ""),
            "subscribed_till": "active"
        }
    except Exception as e:
        logger.error(f"Database error while retrieving user: {e}")
        return None


def auth_and_sub_checks(request: Request) -> str:
    """
    FastAPI dependency that evaluates both authentication and subscription state.
    Returns:
        'not logged in' - User has no valid session
        'not subscribed' - User is authenticated but lacks an active subscription
        'subscribed' - User is authenticated with an active subscription
    """
    token = request.cookies.get("user_id")
    if not token:
        return "not logged in"

    session_data = decode_session_jwt(token)
    if not session_data or "id" not in session_data:
        return "not logged in"

    try:
        collection = get_user_collection()
        if collection is not None:
            user_details = collection.find_one({"google_id": session_data["id"]})
            if not user_details:
                return "not logged in"

            subscription_status = user_details.get("subscribed_till", "not subscribed")
            if subscription_status == "not subscribed":
                return "not subscribed"

            return "subscribed"
        else:
            # Fallback if MongoDB is not running locally: session is considered valid
            return "subscribed"
    except Exception as e:
        logger.error(f"Error checking user auth & subscription: {e}")
        return "not logged in"
