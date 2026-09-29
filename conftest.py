from decimal import Decimal
from io import BytesIO

import pytest
from django.core.cache import cache
from PIL import Image
from rest_framework.test import APIClient

from apps.orders.constants import SHIPPING_SETTINGS_ID
from apps.orders.models import ShippingSettings
from apps.users.tests.factories import UserFactory


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture(autouse=True)
def _clear_throttle_counters():
    cache.clear()


@pytest.fixture
def seed_image_png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (10, 10), "#F2C4CE").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def _offline_seed_images(monkeypatch, seed_image_png):
    # seed_demo downloads real product photographs; a test run must not.
    monkeypatch.setattr(
        "apps.catalog.management.commands.seed_demo.fetch_image",
        lambda url: (seed_image_png, "png"),
    )


@pytest.fixture
def shipping_settings(db) -> ShippingSettings:
    # The data migration creates this row, but a transactional test's flush deletes
    # it for every transactional test after it.
    shipping, _ = ShippingSettings.objects.update_or_create(
        pk=SHIPPING_SETTINGS_ID,
        defaults={
            "inside_valley_fee": Decimal("150.00"),
            "outside_valley_fee": Decimal("250.00"),
            "free_shipping_threshold": None,
        },
    )
    return shipping
