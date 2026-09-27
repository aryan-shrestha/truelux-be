from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalog.tests.factories import ProductFactory, ProductVariantFactory
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

URL = reverse("v1:admin-shipping-settings")


def test_staff_read_the_settings(staff_client, shipping_settings):
    response = staff_client.get(URL)

    assert response.status_code == 200
    assert set(response.data) == {
        "inside_valley_fee",
        "outside_valley_fee",
        "free_shipping_threshold",
        "updated_at",
    }
    assert response.data["inside_valley_fee"] == "150.00"
    assert response.data["free_shipping_threshold"] is None


def test_a_patch_changes_only_the_fields_sent(staff_client, shipping_settings):
    response = staff_client.patch(
        URL, {"free_shipping_threshold": "8000.00", "outside_valley_fee": "300"}, format="json"
    )

    assert response.status_code == 200
    assert response.data["free_shipping_threshold"] == "8000.00"
    assert response.data["outside_valley_fee"] == "300.00"
    assert response.data["inside_valley_fee"] == "150.00"
    shipping_settings.refresh_from_db()
    assert shipping_settings.free_shipping_threshold == Decimal("8000.00")


def test_a_null_threshold_switches_free_shipping_off(staff_client, shipping_settings):
    shipping_settings.free_shipping_threshold = Decimal("8000.00")
    shipping_settings.save()

    response = staff_client.patch(URL, {"free_shipping_threshold": None}, format="json")

    assert response.status_code == 200
    assert response.data["free_shipping_threshold"] is None


def test_a_zero_fee_is_allowed(staff_client, shipping_settings):
    response = staff_client.patch(URL, {"inside_valley_fee": "0.00"}, format="json")

    assert response.status_code == 200
    assert response.data["inside_valley_fee"] == "0.00"


@pytest.mark.parametrize(
    "body",
    [
        {"inside_valley_fee": "-1.00"},
        {"outside_valley_fee": "-0.01"},
        {"free_shipping_threshold": "0"},
        {"free_shipping_threshold": "-5.00"},
        {"inside_valley_fee": None},
        {"outside_valley_fee": "lots"},
    ],
)
def test_invalid_values_are_400(staff_client, shipping_settings, body):
    response = staff_client.patch(URL, body, format="json")

    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"
    field = next(iter(body))
    assert field in response.data["error"]["details"]


def test_non_staff_are_403(shipping_settings):
    client = APIClient()
    client.force_authenticate(user=UserFactory.create())

    assert client.patch(URL, {"inside_valley_fee": "0"}, format="json").status_code == 403
    shipping_settings.refresh_from_db()
    assert shipping_settings.inside_valley_fee == Decimal("150.00")


def test_a_patch_changes_the_next_quote(staff_client, api_client, shipping_settings):
    product = ProductFactory.create(is_published=True, base_price=Decimal("3200.00"))
    variant = ProductVariantFactory.create(product=product, stock_quantity=5)
    body = {"items": [{"variant_id": str(variant.pk), "quantity": 2}], "district": "Lalitpur"}

    before = api_client.post(reverse("v1:checkout-quote"), body, format="json").data
    staff_client.patch(URL, {"free_shipping_threshold": "6000.00"}, format="json")
    after = api_client.post(reverse("v1:checkout-quote"), body, format="json").data

    assert (before["shipping_fee"], before["total"]) == ("150.00", "6550.00")
    assert (after["shipping_fee"], after["total"]) == ("0.00", "6400.00")
