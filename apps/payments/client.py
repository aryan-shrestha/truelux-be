from decimal import Decimal
from typing import Any

import requests
from django.conf import settings

from apps.core.logging import get_logger

logger = get_logger(__name__)

INITIATE_PATH = "epayment/initiate/"
LOOKUP_PATH = "epayment/lookup/"

PAISA_PER_RUPEE = 100

COMPLETED_STATUS = "Completed"


class KhaltiError(Exception):
    """The gateway could not be reached or did not answer in its own terms.

    Not a DomainError: it means a broken integration or an outage, not a customer
    whose request was rejected. Callers translate it.
    """


def to_paisa(amount: Decimal) -> int:
    # Khalti's boundary is integer paisa; the database stores Decimal rupees.
    # Sending a Decimal unconverted charges a hundredth of the intended amount.
    return int(amount * PAISA_PER_RUPEE)


def to_rupees(paisa: int) -> Decimal:
    return Decimal(paisa) / PAISA_PER_RUPEE


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        response = requests.post(
            f"{settings.KHALTI_BASE_URL.rstrip('/')}/{path}",
            json=payload,
            # The `Key ` prefix is not optional: omitting it is a distinct upstream
            # failure ("Authentication credentials were not provided") from passing
            # a wrong key ("Invalid token").
            headers={"Authorization": f"Key {settings.KHALTI_SECRET_KEY}"},
            timeout=settings.KHALTI_TIMEOUT,
        )
    except requests.RequestException as exc:
        # The payload is never logged: it carries the customer's name, email and
        # phone, and the header carries the secret key.
        logger.error("khalti.request_failed", path=path)
        raise KhaltiError(f"Khalti request to {path} failed.") from exc

    try:
        body = response.json()
    except ValueError as exc:
        logger.error("khalti.unreadable_response", path=path, http_status=response.status_code)
        raise KhaltiError(f"Khalti returned a non-JSON response from {path}.") from exc

    return dict(body)


def initiate(
    *,
    amount: Decimal,
    purchase_order_id: str,
    purchase_order_name: str,
    customer_name: str,
    customer_email: str,
    customer_phone: str,
) -> dict[str, Any]:
    """Raises KhaltiError when the gateway is unreachable or rejects the request.

    Returns Khalti's body, which carries `pidx` and `payment_url`.
    """
    body = _post(
        INITIATE_PATH,
        {
            "return_url": settings.KHALTI_RETURN_URL,
            "website_url": settings.STOREFRONT_URL,
            # An int satisfies both readings of Khalti's own inconsistent samples,
            # one of which documents "A valid integer is required."
            "amount": to_paisa(amount),
            "purchase_order_id": purchase_order_id,
            "purchase_order_name": purchase_order_name,
            "customer_info": {
                "name": customer_name,
                "email": customer_email,
                "phone": customer_phone,
            },
        },
    )

    if not body.get("pidx") or not body.get("payment_url"):
        # Validation failures carry `error_key`, authentication failures carry
        # `status_code`; there is no single error shape to parse, so the absence of
        # what was asked for is the reliable signal.
        logger.error("khalti.initiate_rejected", purchase_order_id=purchase_order_id)
        raise KhaltiError("Khalti did not return a payment link.")

    return body


def lookup(*, pidx: str) -> dict[str, Any]:
    """Raises KhaltiError when the gateway is unreachable or reports no status.

    Returns Khalti's body, which carries `status` and `total_amount`.
    """
    body = _post(LOOKUP_PATH, {"pidx": pidx})

    # `Expired` and `User canceled` arrive with HTTP 400 and a perfectly good body.
    # Judging by the status code would turn the two most ordinary customer outcomes
    # into gateway errors, so the body is read first and the code is not consulted.
    #
    # Both fields are checked here so callers can index them: an unknown pidx comes
    # back as {"detail": "Not found.", "error_key": "validation_error"}, which has
    # neither, and Khalti's two error envelopes are too different to recognise.
    if not body.get("status") or body.get("total_amount") is None:
        logger.error("khalti.unusable_lookup_response")
        raise KhaltiError("Khalti returned no usable status for this payment.")

    return body
