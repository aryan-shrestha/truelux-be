from typing import Any
from unittest import mock

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.cache import caches
from django.urls import reverse
from rest_framework.test import APIRequestFactory
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from apps.core.throttling import ResilientAnonRateThrottle


class BrokenCache:
    """Stands in for Redis being unreachable."""

    def get(self, *args: Any, **kwargs: Any) -> Any:
        raise ConnectionError("redis down")

    def set(self, *args: Any, **kwargs: Any) -> Any:
        raise ConnectionError("redis down")


@pytest.fixture(autouse=True)
def _clear_fallback_cache(settings):
    caches[settings.THROTTLE_FALLBACK_CACHE_ALIAS].clear()
    yield
    caches[settings.THROTTLE_FALLBACK_CACHE_ALIAS].clear()


@pytest.fixture
def anon_request():
    request = APIRequestFactory().get("/")
    request.META["REMOTE_ADDR"] = "203.0.113.7"
    request.user = AnonymousUser()
    return request


def _throttle(rate: str) -> ResilientAnonRateThrottle:
    throttle = ResilientAnonRateThrottle()
    throttle.num_requests, throttle.duration = throttle.parse_rate(rate)
    return throttle


def test_a_shared_backend_outage_still_enforces_the_limit_per_process(anon_request):
    throttle = _throttle("2/minute")

    with mock.patch.object(SimpleRateThrottle, "cache", BrokenCache()):
        allowed = [throttle.allow_request(anon_request, APIView()) for _ in range(4)]

    assert allowed == [True, True, False, False]


def test_the_fallback_counts_in_the_dedicated_cache_alias(anon_request, settings):
    throttle = _throttle("5/minute")

    with mock.patch.object(SimpleRateThrottle, "cache", BrokenCache()):
        throttle.allow_request(anon_request, APIView())

    fallback = caches[settings.THROTTLE_FALLBACK_CACHE_ALIAS]
    assert fallback.get(throttle.get_cache_key(anon_request, APIView())) is not None


def test_the_shared_backend_is_restored_after_a_fallback(anon_request):
    throttle = _throttle("5/minute")
    broken = BrokenCache()

    with mock.patch.object(SimpleRateThrottle, "cache", broken):
        throttle.allow_request(anon_request, APIView())

        assert throttle.cache is broken


def test_a_cache_outage_does_not_turn_a_request_into_a_500(api_client):
    # The schema endpoint carries the default throttles; health deliberately does not.
    with mock.patch.object(SimpleRateThrottle, "cache", BrokenCache()):
        response = api_client.get(reverse("schema"))

    assert response.status_code == 200
