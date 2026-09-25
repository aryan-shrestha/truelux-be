from unittest import mock

import pytest
from django.core.management import call_command
from django.db import connection
from django.urls import reverse
from rest_framework.throttling import SimpleRateThrottle

DATABASE_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    },
}


@pytest.mark.django_db
def test_throttle_counts_in_the_database_cache_table(api_client, settings):
    settings.CACHES = DATABASE_CACHE
    call_command("createcachetable")

    with mock.patch.object(
        SimpleRateThrottle,
        "THROTTLE_RATES",
        {**SimpleRateThrottle.THROTTLE_RATES, "catalog": "2/minute"},
    ):
        statuses = [api_client.get(reverse("v1:category-list")).status_code for _ in range(3)]

    assert statuses == [200, 200, 429]
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM django_cache WHERE cache_key LIKE %s", ["%throttle%"])
        assert cursor.fetchone()[0] >= 1
