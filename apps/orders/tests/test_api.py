import uuid
from unittest import mock

import pytest
from django.urls import reverse
from rest_framework.throttling import SimpleRateThrottle

from apps.orders.constants import OrderStatus
from apps.orders.tests.factories import OrderFactory, OrderItemFactory

pytestmark = pytest.mark.django_db


def _rates(**overrides):
    return mock.patch.object(
        SimpleRateThrottle,
        "THROTTLE_RATES",
        {**SimpleRateThrottle.THROTTLE_RATES, **overrides},
    )


def _detail_url(order):
    return reverse("v1:order-detail", args=[order.access_token])


def test_order_detail_by_access_token_returns_200(api_client):
    order = OrderFactory.create(status=OrderStatus.SHIPPED)
    OrderItemFactory.create(order=order, product_name="Rose Milk Cleanser", quantity=2)

    response = api_client.get(_detail_url(order))

    assert response.status_code == 200
    assert response.data["order_number"] == order.order_number
    assert response.data["status"] == "shipped"
    assert response.data["items"][0]["product_name"] == "Rose Milk Cleanser"
    assert response.data["items"][0]["quantity"] == 2


def test_order_detail_renders_the_address_as_one_object(api_client):
    order = OrderFactory.create(full_name="Asha Rai", city="Kathmandu")

    response = api_client.get(_detail_url(order))

    assert response.data["shipping"]["full_name"] == "Asha Rai"
    assert response.data["shipping"]["city"] == "Kathmandu"
    assert "address_line" not in response.data


def test_order_detail_with_wrong_token_returns_404(api_client):
    OrderFactory.create()

    response = api_client.get(reverse("v1:order-detail", args=[uuid.uuid4()]))

    assert response.status_code == 404
    assert response.data["error"]["code"] == "not_found"


def test_order_response_never_contains_access_token(api_client):
    order = OrderFactory.create()
    OrderItemFactory.create(order=order)

    response = api_client.get(_detail_url(order))

    assert str(order.access_token) not in str(response.data)
    assert "access_token" not in response.data


@pytest.mark.parametrize("item_count", [2, 6])
def test_order_detail_query_count_is_constant(api_client, django_assert_num_queries, item_count):
    order = OrderFactory.create()
    for _ in range(item_count):
        OrderItemFactory.create(order=order)

    # The order and its items. The line snapshots mean rendering never reaches the
    # catalogue, so no join is needed and none should appear.
    with django_assert_num_queries(2):
        response = api_client.get(_detail_url(order))

    assert len(response.data["items"]) == item_count


def test_lookup_returns_the_order_for_a_matching_number_and_email(api_client):
    order = OrderFactory.create(email="customer@example.com")
    OrderItemFactory.create(order=order)

    response = api_client.post(
        reverse("v1:order-lookup"),
        {"order_number": order.order_number, "email": "customer@example.com"},
    )

    assert response.status_code == 200
    assert response.data["order_number"] == order.order_number
    assert str(order.access_token) not in str(response.data)


def test_lookup_matches_email_case_insensitively(api_client):
    order = OrderFactory.create(email="customer@example.com")

    response = api_client.post(
        reverse("v1:order-lookup"),
        {"order_number": order.order_number, "email": "Customer@Example.COM"},
    )

    assert response.status_code == 200


def test_lookup_with_mismatched_email_returns_404(api_client):
    order = OrderFactory.create(email="customer@example.com")

    response = api_client.post(
        reverse("v1:order-lookup"),
        {"order_number": order.order_number, "email": "someone@example.com"},
    )

    assert response.status_code == 404
    assert response.data["error"]["code"] == "not_found"


def test_lookup_for_unknown_order_returns_identical_404(api_client):
    order = OrderFactory.create(email="customer@example.com")

    mismatched = api_client.post(
        reverse("v1:order-lookup"),
        {"order_number": order.order_number, "email": "someone@example.com"},
    )
    unknown = api_client.post(
        reverse("v1:order-lookup"),
        {"order_number": "TL-2026-999999", "email": "someone@example.com"},
    )

    # Byte-identical, or the fallback confirms which address placed which order.
    assert mismatched.status_code == unknown.status_code == 404
    assert mismatched.data == unknown.data


def test_lookup_without_an_order_number_returns_400(api_client):
    response = api_client.post(reverse("v1:order-lookup"), {"email": "customer@example.com"})

    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"


def test_lookup_rejects_get(api_client):
    response = api_client.get(reverse("v1:order-lookup"))

    assert response.status_code == 405
    assert response.data["error"]["code"] == "method_not_allowed"


def test_exceeding_lookup_throttle_returns_429(api_client):
    order = OrderFactory.create(email="customer@example.com")
    payload = {"order_number": order.order_number, "email": "customer@example.com"}
    url = reverse("v1:order-lookup")

    with _rates(order_lookup="2/minute"):
        statuses = [api_client.post(url, payload).status_code for _ in range(3)]
        response = api_client.post(url, payload)

    assert statuses == [200, 200, 429]
    assert response.data["error"]["code"] == "throttled"


def test_the_token_endpoint_is_not_on_the_lookup_throttle(api_client):
    order = OrderFactory.create()

    with _rates(order_lookup="1/minute"):
        statuses = [api_client.get(_detail_url(order)).status_code for _ in range(3)]

    assert statuses == [200, 200, 200]
