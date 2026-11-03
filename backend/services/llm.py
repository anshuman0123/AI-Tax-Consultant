import os
import logging
from typing import AsyncGenerator, Optional, Dict
from google import genai
from google.genai import types

from backend.config import settings
from backend.services.vector_store import query_tax_context
from backend.database import get_user_collection

logger = logging.getLogger(__name__)

# Function schema for Indian Income Tax vector database retrieval
PINECONE_TAX_TOOL_DECLARATION = {
    "name": "db_calling",
    "description": (
        "Use this function strictly when the query pertains to the Indian Income Tax Act 1961, "
        "tax slabs, exemptions, deductions (e.g. 80C, 80D), capital gains, corporate tax, or related Indian tax law. "
        "Do not invoke this for general conversational, historical, political, or non-tax questions."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "A focused query strictly related to the Indian Income Tax Act 1961",
            }
        },
        "required": ["question"]
    }
}


class LLMService:
    """Service orchestrating Google Gemini LLM generation, RAG routing, and context augmentation."""

    def __init__(self):
        self._client: Optional[genai.Client] = None
        self._user_chats: Dict[str, Any] = {}
        self._supplementary_cache: Optional[str] = None

    def get_client(self) -> Optional[genai.Client]:
        """Initializes and returns the Google GenAI client if configured."""
        if not settings.GEMINI_API_KEY or "your_gemini_api_key" in settings.GEMINI_API_KEY:
            return None

        if self._client is None:
            self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        return self._client

    def _get_or_create_user_chat(self, user_id: str):
        """Retrieves or creates a stateful chat session for a given user ID."""
        client = self.get_client()
        if not client:
            return None

        if user_id not in self._user_chats:
            self._user_chats[user_id] = client.chats.create(model=settings.GEMINI_MODEL)
        return self._user_chats[user_id]

    def reset_user_chat(self, user_id: str):
        """Resets the chat instance for a user."""
        if user_id in self._user_chats:
            del self._user_chats[user_id]

    def _load_supplementary_document(self) -> str:
        """Reads optional local supplementary reference document (e.g. Finance Bill)."""
        if self._supplementary_cache is not None:
            return self._supplementary_cache

        pdf_path = settings.SUPPLEMENTARY_PDF_PATH
        if not pdf_path or not os.path.exists(pdf_path):
            self._supplementary_cache = ""
            return ""

        try:
            from pypdf import PdfReader
            reader = PdfReader(pdf_path)
            extracted = []
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    extracted.append(text)
            self._supplementary_cache = "\n".join(extracted)
            logger.info(f"Loaded {len(reader.pages)} pages from supplementary document: {pdf_path}")
            return self._supplementary_cache
        except Exception as e:
            logger.warning(f"Could not read supplementary document at '{pdf_path}': {e}")
            self._supplementary_cache = ""
            return ""

    def should_query_tax_db(self, question: str) -> bool:
        """
        Classifies whether the user inquiry requires vector database context
        from the Income Tax Act 1961.
        """
        client = self.get_client()
        if not client:
            # Fallback simple keyword heuristic if no active API key
            tax_keywords = ["tax", "itr", "80c", "deduction", "income", "exempt", "slab", "gst", "tds", "salary", "capital gain"]
            return any(kw in question.lower() for kw in tax_keywords)

        try:
            prompt = (
                f"Question: '{question}'\n"
                f"Based on this query, decide whether to call the following function:\n"
                f"{PINECONE_TAX_TOOL_DECLARATION}\n"
                f"Return ONLY 'True' or 'False' and nothing else."
            )
            eval_response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt
            )
            verdict = eval_response.text.strip().lower() if eval_response.text else "false"
            return "true" in verdict
        except Exception as e:
            logger.warning(f"Tax routing evaluation failed: {e}. Defaulting to true for safety.")
            return True

    async def stream_chat_response(self, user_id: str, question: str) -> AsyncGenerator[str, None]:
        """
        Orchestrates RAG retrieval, context construction, and yields streamed response chunks.
        """
        client = self.get_client()

        # Graceful placeholder response if Gemini API key is not yet set
        if not client:
            mock_message = (
                f"**[Demo Mode - API Key Required]**\n\n"
                f"Received inquiry: *\"{question}\"*\n\n"
                f"To enable live AI tax advisory:\n"
                f"1. Open your `.env` file.\n"
                f"2. Add a valid `GEMINI_API_KEY` from [Google AI Studio](https://aistudio.google.com/).\n"
                f"3. Optionally configure `PINECONE_API_KEY` for semantic search across the Income Tax Act 1961.\n\n"
                f"The RAG routing, user authentication, and SSE streaming pipeline are fully operational."
            )
            for word in mock_message.split(" "):
                yield word + " "
            return

        chat = self._get_or_create_user_chat(user_id)
        needs_context = self.should_query_tax_db(question)

        prompt_to_send = question
        if needs_context:
            logger.info("Tax-related query detected. Retrieving context from Pinecone...")
            retrieved_context = query_tax_context(question)
            supplementary_text = self._load_supplementary_document()

            context_block = f"\n\n[Relevant Sections from Income Tax Act 1961]:\n{retrieved_context}"
            if supplementary_text:
                context_block += f"\n\n[Supplementary Finance Document]:\n{supplementary_text[:4000]}"

            prompt_to_send = (
                f"{question}\n\n"
                f"Use the following legal context to formulate your response accurately:\n"
                f"{context_block}"
            )

        full_response_text = ""
        try:
            response_stream = chat.send_message_stream(prompt_to_send)
            for chunk in response_stream:
                if chunk.text:
                    full_response_text += chunk.text
                    yield chunk.text
        except Exception as e:
            logger.error(f"Error streaming response from Gemini: {e}")
            yield f"\n[Error generating response: {str(e)}]"

        # Persist conversation turn to MongoDB if available
        try:
            collection = get_user_collection()
            if collection is not None:
                collection.update_one(
                    {"google_id": user_id},
                    {
                        "$push": {
                            "chats": {
                                "$each": [
                                    {"role": "user", "message": question},
                                    {"role": "AI", "message": full_response_text}
                                ]
                            }
                        }
                    }
                )
        except Exception as db_err:
            logger.warning(f"Failed to record chat history to DB: {db_err}")


llm_service = LLMService()
