import logging
from typing import Optional, Dict, Any
import requests

from backend.config import settings

logger = logging.getLogger(__name__)


class PineconeVectorService:
    """
    Service for querying Pinecone vector database to retrieve
    relevant sections from the Income Tax Act 1961 dataset.
    """

    def __init__(self):
        self.api_key = settings.PINECONE_API_KEY
        self.index_host = settings.PINECONE_INDEX_HOST
        self.namespace = settings.PINECONE_NAMESPACE
        self.top_k = settings.PINECONE_TOP_K

    def is_configured(self) -> bool:
        """Checks if required Pinecone settings are present."""
        return bool(
            self.api_key
            and self.index_host
            and "your_pinecone_api_key" not in self.api_key
        )

    def search(self, question: str) -> str:
        """
        Executes a vector semantic search on the Pinecone index.
        Returns the retrieved textual context.
        """
        if not self.is_configured():
            logger.warning("Pinecone credentials are not configured or using placeholders. Skipping vector search.")
            return "(No external vector database context configured. Answering using general legal knowledge.)"

        try:
            # 1. First attempt: Official Pinecone SDK search if available
            try:
                from pinecone import Pinecone
                pc = Pinecone(api_key=self.api_key)
                index = pc.Index(host=self.index_host)
                results = index.search(
                    namespace=self.namespace,
                    query={
                        "inputs": {"text": question},
                        "top_k": self.top_k
                    }
                )
                return str(results)
            except Exception as sdk_err:
                logger.debug(f"Pinecone SDK search failed or not supported in this environment: {sdk_err}. Falling back to REST API.")

            # 2. Fallback: Direct Pinecone REST API endpoint
            clean_host = self.index_host.replace("https://", "").rstrip("/")
            url = f"https://{clean_host}/records/namespaces/{self.namespace}/search"
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Api-Key": self.api_key,
                "X-Pinecone-API-Version": "unstable"
            }
            payload = {
                "query": {
                    "inputs": {"text": question},
                    "top_k": self.top_k
                }
            }

            response = requests.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.text
            else:
                logger.error(f"Pinecone API returned status {response.status_code}: {response.text}")
                return f"(Vector database query returned status code {response.status_code})"

        except Exception as e:
            logger.error(f"Error querying Pinecone index: {e}")
            return f"(Unable to retrieve vector context: {str(e)})"


vector_service = PineconeVectorService()


def query_tax_context(question: str) -> str:
    """Helper function to retrieve tax context from vector store."""
    return vector_service.search(question)
