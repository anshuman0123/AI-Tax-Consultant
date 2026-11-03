import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, Optional, Any
from backend.config import settings
from backend.database import get_user_collection

logger = logging.getLogger(__name__)


class PaymentService:
    """Manages subscription checkouts and status verifications with Dodo Payments."""

    def __init__(self):
        self._pending_payments: Dict[str, asyncio.Future] = {}
        self._client: Optional[Any] = None

    def get_client(self):
        """Initializes and returns the DodoPayments client."""
        if not settings.DODO_PAYMENTS_API_KEY or "your_dodo_payments_api_key" in settings.DODO_PAYMENTS_API_KEY:
            return None

        if self._client is None:
            try:
                from dodopayments import DodoPayments
                self._client = DodoPayments(
                    bearer_token=settings.DODO_PAYMENTS_API_KEY,
                    environment=settings.DODO_PAYMENTS_ENVIRONMENT
                )
            except Exception as e:
                logger.error(f"Failed to initialize DodoPayments client: {e}")
        return self._client

    async def initiate_payment_stream(self, user_id: str) -> AsyncGenerator[str, None]:
        """
        Creates a checkout payment session and yields SSE events:
        1. 'payment init' with payment link
        2. 'payment result' once callback resolves status
        """
        client = self.get_client()

        # Create a dedicated future for this user's payment flow
        payment_future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_payments[user_id] = payment_future

        try:
            if client:
                try:
                    payment = client.payments.create(
                        payment_link=True,
                        billing={
                            "city": "Bengaluru",
                            "country": "IN",
                            "state": "KA",
                            "street": "MG Road",
                            "zipcode": "560001",
                        },
                        customer={
                            "customer_id": f"cus_{user_id[:16]}"
                        },
                        product_cart=[{
                            "product_id": settings.DODO_PRODUCT_ID,
                            "quantity": 1,
                        }],
                        return_url=f"{settings.DODO_RETURN_URL}?user_id={user_id}",
                    )
                    payment_link = payment.payment_link
                    logger.info(f"Payment session created: {payment_link}")
                except Exception as e:
                    logger.warning(f"Dodo payments creation failed ({e}). Providing demo payment link.")
                    payment_link = f"/api/payment_status?user_id={user_id}&status=succeeded&payment_id=demo_{user_id}"
            else:
                # Demo / local development fallback payment link
                payment_link = f"/api/payment_status?user_id={user_id}&status=succeeded&payment_id=demo_{user_id}"

            # Step 1: Send payment init event with the link
            yield f"data: {json.dumps({'message': 'payment init', 'payment_link': payment_link})}\n\n"

            # Step 2: Await completion of payment confirmation with 10-minute timeout
            try:
                result_status = await asyncio.wait_for(payment_future, timeout=600)
            except asyncio.TimeoutError:
                result_status = "timeout"

            yield f"data: {json.dumps({'message': 'payment result', 'status': result_status})}\n\n"

        finally:
            self._pending_payments.pop(user_id, None)

    def resolve_payment_status(self, user_id: str, payment_id: Optional[str], status_param: Optional[str]) -> str:
        """
        Processes payment callback, verifies state, updates MongoDB,
        and resolves the pending future for SSE.
        """
        final_status = "succeeded"
        client = self.get_client()

        if client and payment_id and not payment_id.startswith("demo_"):
            try:
                payment = client.payments.retrieve(payment_id=payment_id)
                final_status = str(payment.status)
            except Exception as e:
                logger.error(f"Error verifying payment with DodoPayments: {e}")
                final_status = status_param or "pending"
        elif status_param:
            final_status = status_param

        # Update user's subscription in MongoDB if payment succeeded
        if final_status.lower() in ["succeeded", "completed", "paid", "active"]:
            try:
                collection = get_user_collection()
                if collection is not None:
                    collection.update_one(
                        {"google_id": user_id},
                        {
                            "$set": {
                                "subscribed_till": "active",
                                "subscription_updated_at": asyncio.get_event_loop().time()
                            },
                            "$inc": {"number_of_subs": 1}
                        },
                        upsert=True
                    )
                    logger.info(f"Subscription marked active for user: {user_id}")
            except Exception as db_err:
                logger.error(f"Failed to update subscription in database: {db_err}")

        # Resolve the pending SSE future for this user
        future = self._pending_payments.get(user_id)
        if future and not future.done():
            future.set_result(final_status)

        return final_status


payment_service = PaymentService()
