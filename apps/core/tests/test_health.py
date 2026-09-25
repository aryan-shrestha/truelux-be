from unittest import mock

import pytest
from django.db import connections
from django.urls import reverse

from apps.core.middleware import REQUEST_ID_HEADER


@pytest.mark.django_db
def test_liveness_is_public_and_touches_no_database(api_client, django_assert_num_queries):
    url = reverse("health:live")

    with django_assert_num_queries(0):
        response = api_client.get(url)

    assert response.status_code == 200
    assert response.data["status"] == "ok"


@pytest.mark.django_db
def test_readiness_is_public_and_reports_both_checks_ok(api_client):
    url = reverse("health:ready")

    response = api_client.get(url)

    assert response.status_code == 200
    assert response.data["status"] == "ready"
    assert response.data["checks"]["database"] == "ok"
    assert response.data["checks"]["cache"] == "ok"


@pytest.mark.django_db
def test_readiness_returns_503_without_exception_text_when_cache_is_down(api_client):
    url = reverse("health:ready")

    with mock.patch(
        "apps.core.views.cache.set", side_effect=ConnectionError("redis://secret@host")
    ):
        response = api_client.get(url)

    assert response.status_code == 503
    assert response.data["status"] == "not_ready"
    assert response.data["checks"]["cache"] == "error"
    assert "secret" not in str(response.data)


@pytest.mark.django_db
def test_readiness_returns_503_without_exception_text_when_database_is_down(api_client):
    url = reverse("health:ready")

    with mock.patch.object(connections["default"], "cursor", side_effect=ConnectionError("boom")):
        response = api_client.get(url)

    assert response.status_code == 503
    assert response.data["checks"]["database"] == "error"
    assert "boom" not in str(response.data)


def test_response_carries_a_request_id_header(api_client):
    response = api_client.get(reverse("health:live"))

    assert response[REQUEST_ID_HEADER]


def test_upstream_request_id_is_preserved(api_client):
    response = api_client.get(reverse("health:live"), headers={"x-request-id": "trace-abc"})

    assert response[REQUEST_ID_HEADER] == "trace-abc"


def test_an_unusable_upstream_request_id_is_replaced(api_client):
    response = api_client.get(reverse("health:live"), headers={"x-request-id": "a b\tc"})

    assert response[REQUEST_ID_HEADER] != "a b\tc"


def test_an_oversized_upstream_request_id_is_replaced(api_client):
    response = api_client.get(reverse("health:live"), headers={"x-request-id": "x" * 500})

    assert len(response[REQUEST_ID_HEADER]) <= 64
