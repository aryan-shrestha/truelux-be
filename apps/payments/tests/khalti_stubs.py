"""Stand-ins for Khalti's HTTP responses, shared by the payments and checkout tests.

A plain module rather than a conftest, because `apps/orders/tests` needs it too and
a fixture in one test package is not visible from another.
"""

from typing import Any


class FakeResponse:
    """Stands in for a `requests` response, body first.

    Khalti answers `Expired` and `User canceled` with HTTP 400 and a perfectly good
    body, so a stub that only models 2xx would hide the case most worth testing.
    """

    def __init__(self, body: dict[str, Any] | None, status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        if self._body is None:
            raise ValueError("no JSON body")
        return self._body


INITIATE_BODY = {
    "pidx": "pidx-1",
    "payment_url": "https://test-pay.khalti.invalid/?pidx=pidx-1",
    "expires_at": "2026-09-21T16:26:16.471649+05:45",
    "expires_in": 1800,
}


def lookup_body(
    status: str = "Completed", total_amount: int = 465000, transaction_id: str = "txn-1"
) -> dict[str, Any]:
    return {
        "pidx": "pidx-1",
        "total_amount": total_amount,
        "status": status,
        "transaction_id": transaction_id,
        "fee": 0,
        "refunded": False,
    }
