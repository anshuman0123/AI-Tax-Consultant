import os
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, Depends, HTTPException, Query, Header, status
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.database import db_manager, get_user_collection
from backend.models import CredentialRequest, QuestionRequest, StatusResponse
from backend.auth import (
    verify_google_token,
    create_session_jwt,
    decode_session_jwt,
    auth_and_sub_checks,
    get_current_user_from_cookie,
)
from backend.services.llm import llm_service
from backend.services.payment import payment_service

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ai_tax_consultant")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for clean startup and teardown."""
    logger.info("Starting AI Tax Consultant server...")
    yield
    logger.info("Shutting down AI Tax Consultant server...")
    db_manager.close()


app = FastAPI(
    title="AI Tax Consultant API",
    description="Intelligent Indian Income Tax RAG Consultant with Pinecone, Gemini, and DodoPayments",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Frontend Directory path
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))


# ------------------------------------------------------------------------------
# Authentication & Status Endpoints
# ------------------------------------------------------------------------------

@app.get("/api/", response_model=StatusResponse)
@app.get("/api/status", response_model=StatusResponse)
async def check_status(auth_status: str = Depends(auth_and_sub_checks)):
    """Verifies the caller's authentication and subscription status."""
    return JSONResponse(content={"status": auth_status})


@app.post("/api/login")
async def login_with_google(payload: CredentialRequest):
    """
    Validates Google OAuth ID token, upserts user profile into MongoDB,
    and issues an HttpOnly session cookie.
    """
    try:
        idinfo = verify_google_token(payload.credential)
        user_id = idinfo.get("sub") or idinfo.get("id")
        email = idinfo.get("email", "")
        name = idinfo.get("name", "Tax User")
        picture = idinfo.get("picture", "")

        if not user_id:
            raise HTTPException(status_code=400, detail="Invalid credential token: missing user ID.")

        user_doc = {
            "google_id": user_id,
            "email": email,
            "name": name,
            "picture": picture,
        }

        # Upsert user record in MongoDB
        try:
            collection = get_user_collection()
            if collection is not None:
                collection.update_one(
                    {"google_id": user_id},
                    {
                        "$set": user_doc,
                        "$setOnInsert": {
                            "chats": [],
                            "subscribed_till": "not subscribed",
                            "number_of_subs": 0,
                        }
                    },
                    upsert=True
                )
        except Exception as db_err:
            logger.warning(f"Could not persist user to MongoDB ({db_err}). Proceeding with cookie session.")

        # Create session JWT
        session_token = create_session_jwt({
            "id": user_id,
            "email": email,
            "name": name,
            "picture": picture
        })

        response = JSONResponse(content={
            "message": "Login successful",
            "user": user_doc
        })

        # Set secure HttpOnly session cookie
        response.set_cookie(
            key="user_id",
            value=session_token,
            max_age=settings.JWT_EXPIRATION_DAYS * 24 * 60 * 60,
            httponly=True,
            samesite="lax",
            secure=False if settings.ENVIRONMENT == "development" else True,
            path="/"
        )
        return response

    except ValueError as ve:
        logger.error(f"Authentication validation error: {ve}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google token")
    except Exception as e:
        logger.error(f"Unexpected login error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Login failed")


@app.post("/api/logout")
async def logout():
    """Clears the session cookie."""
    response = JSONResponse(content={"message": "Logged out successfully"})
    response.delete_cookie(key="user_id", path="/")
    return response


# ------------------------------------------------------------------------------
# AI Tax Consultation (RAG + SSE Streaming) Endpoints
# ------------------------------------------------------------------------------

@app.get("/api/answer")
@app.post("/api/answer")
async def get_tax_answer(
    req: Request,
    question: Optional[str] = Query(None),
    question_header: Optional[str] = Header(None, alias="Question"),
    auth_state: str = Depends(auth_and_sub_checks)
):
    """
    RAG AI Consultation Endpoint.
    Streams AI response using retrieved vector context from the Income Tax Act 1961.
    """
    if auth_state == "not logged in":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    if auth_state == "not subscribed":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active subscription required.")

    # Extract user ID from session cookie
    token = req.cookies.get("user_id")
    session_data = decode_session_jwt(token) if token else None
    user_id = session_data.get("id", "anonymous_user") if session_data else "anonymous_user"

    # Support question from: 1) JSON body, 2) Query param, 3) Header
    final_question = question or question_header
    if not final_question and req.method == "POST":
        try:
            body = await req.json()
            final_question = body.get("question")
        except Exception:
            pass

    if not final_question:
        raise HTTPException(status_code=400, detail="Missing question parameter.")

    async def stream_generator():
        async for chunk in llm_service.stream_chat_response(user_id=user_id, question=final_question):
            yield chunk

    return StreamingResponse(stream_generator(), media_type="text/plain; charset=utf-8")


@app.post("/api/new_chat")
async def new_chat(req: Request):
    """Resets the active conversational context for the current user."""
    token = req.cookies.get("user_id")
    session_data = decode_session_jwt(token) if token else None
    if session_data and "id" in session_data:
        llm_service.reset_user_chat(session_data["id"])
    return JSONResponse(content={"message": "New chat session initialized."})


# ------------------------------------------------------------------------------
# Payment & Subscription Endpoints (Dodo Payments)
# ------------------------------------------------------------------------------

@app.get("/api/create_payment")
async def create_payment(req: Request):
    """SSE endpoint initiating subscription checkout and streaming real-time status."""
    token = req.cookies.get("user_id")
    session_data = decode_session_jwt(token) if token else None
    user_id = session_data.get("id", "guest_customer") if session_data else "guest_customer"

    return StreamingResponse(
        payment_service.initiate_payment_stream(user_id=user_id),
        media_type="text/event-stream"
    )


@app.get("/api/payment_status")
@app.get("/payment_status")
async def payment_status_callback(
    user_id: Optional[str] = Query(None),
    payment_id: Optional[str] = Query(None),
    status_param: Optional[str] = Query(None, alias="status")
):
    """Callback landing page displayed when payment provider redirects back."""
    target_user_id = user_id or "guest_customer"
    resolved_status = payment_service.resolve_payment_status(
        user_id=target_user_id,
        payment_id=payment_id,
        status_param=status_param
    )

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Payment Status - TaxAssist</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
        <style>
            body {{
                font-family: 'Inter', sans-serif;
                background: #0f172a;
                color: #f8fafc;
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100vh;
                margin: 0;
            }}
            .card {{
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 16px;
                padding: 2.5rem;
                text-align: center;
                max-width: 440px;
                box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
            }}
            .badge {{
                display: inline-block;
                padding: 6px 16px;
                border-radius: 9999px;
                background: #10b981;
                color: #064e3b;
                font-weight: 700;
                font-size: 0.875rem;
                margin-bottom: 1rem;
                text-transform: uppercase;
            }}
            h1 {{ font-size: 1.5rem; margin-bottom: 0.5rem; }}
            p {{ color: #94a3b8; font-size: 0.95rem; line-height: 1.5; }}
            .btn {{
                display: inline-block;
                margin-top: 1.5rem;
                padding: 10px 20px;
                background: #6366f1;
                color: white;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 600;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <span class="badge">Confirmation</span>
            <h1>Payment Status: {resolved_status.capitalize()}</h1>
            <p>Your subscription is now updated. You can close this window or click below to return to your workspace.</p>
            <a href="/main.html" class="btn">Return to Assistant</a>
        </div>
        <script>
            setTimeout(() => {{
                if (window.opener) {{
                    window.close();
                }}
            }}, 4000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# ------------------------------------------------------------------------------
# Frontend Static Files & Page Routes
# ------------------------------------------------------------------------------

if os.path.exists(FRONTEND_DIR):
    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

    @app.get("/auth.html", include_in_schema=False)
    @app.get("/auth", include_in_schema=False)
    async def serve_auth():
        return FileResponse(os.path.join(FRONTEND_DIR, "auth.html"))

    @app.get("/main.html", include_in_schema=False)
    @app.get("/chat", include_in_schema=False)
    async def serve_chat():
        return FileResponse(os.path.join(FRONTEND_DIR, "main.html"))

    @app.get("/payment.html", include_in_schema=False)
    @app.get("/payment", include_in_schema=False)
    async def serve_payment():
        return FileResponse(os.path.join(FRONTEND_DIR, "payment.html"))

    # Mount remaining frontend static assets
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
