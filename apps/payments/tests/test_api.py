import threading
from decimal import Decimal

import pytest
import requests
from django.core.cache import caches
from django.db import connections
from django.urls import reverse

from apps.orders.constants import OrderStatus, PaymentMethod
from apps.orders.tests.factories import OrderFactory
from apps.payments.models import Payment, PaymentStatus
from apps.payments.services import verify_khalti_payment
from apps.payments.tests.factories import PaymentFactory
from apps.payments.tests.khalti_stubs import FakeResponse, lookup_body

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_throttle_counters(settings):
    for alias in (settings.THROTTLE_FALLBACK_CACHE_ALIAS, "default"):
        caches[alias].clear()


def _pending_khalti_payment():
    order = OrderFactory.create(status=OrderStatus.PENDING, total=Decimal("4650.00"))
    return PaymentFactory.create(
        order=order, method=PaymentMethod.KHALTI, pidx="pidx-1", amount=order.total
    )


def _return(api_client, **params):
    return api_client.get(reverse("v1:khalti-return"), params)


def test_return_with_completed_lookup_marks_order_paid(api_client, khalti_post):
    payment = _pending_khalti_payment()
    khalti_post.return_value = FakeResponse(lookup_body())

    response = _return(api_client, pidx="pidx-1")

    assert response.status_code == 302
    payment.order.refresh_from_db()
    assert payment.order.status == OrderStatus.PAID


def test_return_redirects_to_the_storefront_with_the_access_token(
    api_client, khalti_post, settings
):
    payment = _pending_khalti_payment()
    khalti_post.return_value = FakeResponse(lookup_body())

    response = _return(api_client, pidx="pidx-1")

    expected = f"{settings.STOREFRONT_URL}/orders/{payment.order.access_token}"
    assert response["Location"] == expected


def test_return_ignores_status_parameter_from_query_string(api_client, khalti_post):
    payment = _pending_khalti_payment()
    khalti_post.return_value = FakeResponse(lookup_body(status="User canceled"), status_code=400)

    # The single most important test here. Every parameter in this redirect is
    # editable by whoever holds the URL; believing `status` is the difference
    # between a store and a free shop.
    response = _return(
        api_client, pidx="pidx-1", status="Completed", amount="465000", transaction_id="forged"
    )

    assert response.status_code == 302
    assert "reason=payment_not_completed" in response["Location"]
    payment.order.refresh_from_db()
    assert payment.order.status == OrderStatus.PENDING
    assert payment.order.status != OrderStatus.PAID


def test_return_with_user_canceled_lookup_leaves_order_pending(api_client, khalti_post):
    payment = _pending_khalti_payment()
    khalti_post.return_value = FakeResponse(lookup_body(status="User canceled"), status_code=400)

    _return(api_client, pidx="pidx-1")

    payment.order.refresh_from_db()
    payment.refresh_from_db()
    assert payment.order.status == OrderStatus.PENDING
    assert payment.status == PaymentStatus.FAILED


def test_return_for_a_failed_payment_redirects_with_a_reason(api_client, khalti_post, settings):
    _pending_khalti_payment()
    khalti_post.return_value = FakeResponse(lookup_body(status="Expired"), status_code=400)

    response = _return(api_client, pidx="pidx-1")

    assert response["Location"] == (
        f"{settings.STOREFRONT_URL}/orders/failed?reason=payment_not_completed"
    )


def test_return_with_amount_mismatch_returns_422_and_does_not_fulfil(api_client, khalti_post):
    payment = _pending_khalti_payment()
    khalti_post.return_value = FakeResponse(lookup_body(total_amount=100))

    response = _return(api_client, pidx="pidx-1")

    # The browser gets a reason it can render; the 422 is what the service raised.
    assert "reason=payment_amount_mismatch" in response["Location"]
    payment.order.refresh_from_db()
    assert payment.order.status == OrderStatus.PENDING


def test_second_return_for_same_pidx_does_not_double_fulfil(api_client, khalti_post):
    payment = _pending_khalti_payment()
    khalti_post.return_value = FakeResponse(lookup_body())

    first = _return(api_client, pidx="pidx-1")
    second = _return(api_client, pidx="pidx-1")

    assert first["Location"] == second["Location"]
    payment.order.refresh_from_db()
    assert payment.order.status == OrderStatus.PAID
    assert Payment.objects.filter(status=PaymentStatus.COMPLETED).count() == 1


def test_a_gateway_outage_redirects_rather_than_erroring(api_client, khalti_post, settings):
    payment = _pending_khalti_payment()
    khalti_post.side_effect = requests.ConnectionError("no route to host")

    response = _return(api_client, pidx="pidx-1")

    assert response.status_code == 302
    assert response["Location"] == (
        f"{settings.STOREFRONT_URL}/orders/failed?reason=payment_gateway_unavailable"
    )
    payment.order.refresh_from_db()
    assert payment.order.status == OrderStatus.PENDING


def test_return_with_unknown_pidx_returns_404(api_client, khalti_post):
    response = _return(api_client, pidx="never-issued")

    # Not a redirect: a pidx this system never issued means a hand-crafted URL, not
    # a customer coming back from Khalti.
    assert response.status_code == 404
    assert response.data["error"]["code"] == "not_found"


def test_return_without_a_pidx_returns_404(api_client, khalti_post):
    response = _return(api_client)

    assert response.status_code == 404


# transaction=True, overriding the module marker: the other thread runs on its own
# connection and cannot see data held in an uncommitted test transaction.
@pytest.mark.django_db(transaction=True)
def test_concurrent_returns_fulfil_once(khalti_post):
    payment = _pending_khalti_payment()
    khalti_post.return_value = FakeResponse(lookup_body())

    start = threading.Barrier(2)
    failures: list[Exception] = []

    def come_back_from_khalti() -> None:
        try:
            start.wait(timeout=10)
            verify_khalti_payment(pidx="pidx-1")
        except Exception as exc:  # noqa: BLE001 - an exception here is the assertion
            failures.append(exc)
        finally:
            # Each thread opens its own connection. Leaving one open holds a session
            # on the test database and makes its teardown fail.
            connections.close_all()

    returns = [threading.Thread(target=come_back_from_khalti) for _ in range(2)]
    for coming_back in returns:
        coming_back.start()
    for coming_back in returns:
        coming_back.join(timeout=30)

    payment.order.refresh_from_db()
    assert payment.order.status == OrderStatus.PAID
    assert Payment.objects.filter(status=PaymentStatus.COMPLETED).count() == 1
    # Neither request errors: the loser finds the payment already completed and
    # returns the same answer, which is what a refreshed return URL must do.
    assert failures == []
