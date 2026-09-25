from decimal import Decimal

import pytest
import requests

from apps.payments import client
from apps.payments.tests.khalti_stubs import FakeResponse, lookup_body

pytestmark = pytest.mark.django_db


def test_amount_is_converted_to_paisa_on_initiate(khalti_post):
    client.initiate(
        amount=Decimal("4650.00"),
        purchase_order_id="TL-2026-000142",
        purchase_order_name="Order TL-2026-000142",
        customer_name="Asha Rai",
        customer_email="customer@example.com",
        customer_phone="9800000000",
    )

    payload = khalti_post.call_args.kwargs["json"]
    assert payload["amount"] == 465000
    # An int satisfies both readings of Khalti's own inconsistent samples, one of
    # which documents "A valid integer is required."
    assert isinstance(payload["amount"], int)


def test_lookup_response_amount_is_converted_to_rupees():
    assert client.to_rupees(465000) == Decimal("4650.00")
    assert client.to_rupees(1000) == Decimal("10.00")


def test_the_authorization_header_carries_the_key_prefix(khalti_post, settings):
    khalti_post.return_value = FakeResponse(lookup_body())

    client.lookup(pidx="pidx-1")

    header = khalti_post.call_args.kwargs["headers"]["Authorization"]
    # Omitting `Key ` is a distinct upstream failure from passing a wrong key.
    assert header == f"Key {settings.KHALTI_SECRET_KEY}"


def test_every_call_carries_a_timeout(khalti_post, settings):
    khalti_post.return_value = FakeResponse(lookup_body())

    client.lookup(pidx="pidx-1")

    assert khalti_post.call_args.kwargs["timeout"] == settings.KHALTI_TIMEOUT


@pytest.mark.parametrize("status", ["Expired", "User canceled"])
def test_expired_and_user_canceled_are_read_from_a_400_body(khalti_post, status):
    khalti_post.return_value = FakeResponse(lookup_body(status=status), status_code=400)

    body = client.lookup(pidx="pidx-1")

    # Judging by the HTTP code would turn the two most ordinary customer outcomes
    # into gateway errors.
    assert body["status"] == status


def test_a_transport_failure_raises_khalti_error(khalti_post):
    khalti_post.side_effect = requests.ConnectionError("no route to host")

    with pytest.raises(client.KhaltiError):
        client.lookup(pidx="pidx-1")


def test_a_non_json_response_raises_khalti_error(khalti_post):
    khalti_post.return_value = FakeResponse(None, status_code=502)

    with pytest.raises(client.KhaltiError):
        client.lookup(pidx="pidx-1")


def test_an_initiate_without_a_payment_link_raises_khalti_error(khalti_post):
    # Khalti's two error envelopes differ -- auth failures carry `status_code`,
    # validation failures carry `error_key` -- so the absence of what was asked for
    # is the reliable signal.
    khalti_post.return_value = FakeResponse(
        {
            "amount": ["Amount should be greater than Rs. 10, that is 1000 paisa."],
            "error_key": "validation_error",
        },
        status_code=400,
    )

    with pytest.raises(client.KhaltiError):
        client.initiate(
            amount=Decimal("5.00"),
            purchase_order_id="TL-2026-000142",
            purchase_order_name="Order TL-2026-000142",
            customer_name="Asha Rai",
            customer_email="customer@example.com",
            customer_phone="9800000000",
        )


def test_secret_key_and_customer_details_are_never_logged(khalti_post, caplog, settings):
    khalti_post.side_effect = requests.ConnectionError("no route to host")

    with pytest.raises(client.KhaltiError):
        client.initiate(
            amount=Decimal("4650.00"),
            purchase_order_id="TL-2026-000142",
            purchase_order_name="Order TL-2026-000142",
            customer_name="Asha Rai",
            customer_email="customer@example.com",
            customer_phone="9800000000",
        )

    assert settings.KHALTI_SECRET_KEY not in caplog.text
    assert "customer@example.com" not in caplog.text
    assert "9800000000" not in caplog.text
