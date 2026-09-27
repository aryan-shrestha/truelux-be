from decimal import Decimal

import pytest
from django.core.cache import cache
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
