import os
from dodopayments import DodoPayments

client = DodoPayments(
    bearer_token =  "bFizq2t5rpGeBVsl.g1j54Jg5a-m6nr5C91cvEvhJLmn7oChGZDltGfhEKGJwpG7v",# "iHPvJgyU9LgVmcrS.Cp3VgjINShQz099eHvtOsjB4FeHGemeTrXHISuy7SguZNlKB",  # This is the default and can be omitted
    # defaults to "live_mode".
    # environment="test_mode",  # or "test_mode"
)

payment = client.payments.create(
    payment_link=True,
    billing={
        "city": "bhubaneswar",
        "country": "IN",
        "state": "Odisha",
        "street": "dumduma",
        "zipcode": "751019",
    },
    customer={
        # "email": "anshumanrout90@gmail.com",
        # "name": "Anshuuuu",
        "customer_id": "cus_gYFZXyj9L0lRejqVDh1qz"
    },
    product_cart=[
        {
            "product_id": "pdt_kL3kYuIFX9BtmYMFmSgqJ",
            "quantity": 1,
        }
    ],
)
# iHPvJgyU9LgVmcrS.Cp3VgjINShQz099eHvtOsjB4FeHGemeTrXHISuy7SguZNlKB
print(payment.payment_link)