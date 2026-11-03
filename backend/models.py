from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class CredentialRequest(BaseModel):
    """Payload sent from Google Sign-In containing the credential JWT."""
    credential: str = Field(..., description="Google ID Token credential")


class QuestionRequest(BaseModel):
    """Payload for submitting a tax inquiry."""
    question: str = Field(..., min_length=1, description="Tax or financial inquiry text")


class UserSession(BaseModel):
    """Payload stored in the encrypted session cookie."""
    id: str = Field(..., description="Google Subject/User ID")
    email: str = Field(..., description="User Email")
    name: Optional[str] = Field(default=None, description="User Full Name")
    picture: Optional[str] = Field(default=None, description="User Profile Picture URL")


class StatusResponse(BaseModel):
    """Generic status response."""
    status: str
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class ChatMessage(BaseModel):
    """Structure for recorded chat dialogue history."""
    role: str = Field(..., description="Role: 'user' or 'AI'")
    message: str = Field(..., description="Message content")
