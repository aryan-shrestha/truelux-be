import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

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
