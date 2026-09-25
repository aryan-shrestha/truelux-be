import uuid

import pytest
from django.urls import URLPattern, reverse
from rest_framework.test import APIClient

from apps.backoffice.urls import urlpatterns
from apps.backoffice.views import StaffAPIView
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

ROUTES = [(pattern.name, list(pattern.pattern.converters)) for pattern in urlpatterns]


def _url(name, converters):
    return reverse(f"v1:{name}", kwargs={key: uuid.uuid4() for key in converters})


@pytest.mark.parametrize(("name", "converters"), ROUTES)
@pytest.mark.parametrize("method", ["get", "post", "patch", "delete"])
def test_anonymous_requests_are_401(api_client, name, converters, method):
    response = getattr(api_client, method)(_url(name, converters))

    assert response.status_code == 401
    assert response.data["error"]["code"] == "authentication_failed"


@pytest.mark.parametrize(("name", "converters"), ROUTES)
@pytest.mark.parametrize("method", ["get", "post", "patch", "delete"])
def test_non_staff_tokens_are_403(name, converters, method):
    client = APIClient()
    client.force_authenticate(user=UserFactory.create())

    response = getattr(client, method)(_url(name, converters))

    assert response.status_code == 403
    assert response.data["error"]["code"] == "permission_denied"


@pytest.mark.parametrize("pattern", urlpatterns, ids=lambda pattern: pattern.name)
def test_every_admin_route_uses_the_staff_policy(pattern: URLPattern):
    assert issubclass(pattern.callback.view_class, StaffAPIView)


def test_a_django_admin_session_is_not_accepted(client):
    client.force_login(UserFactory(is_staff=True, is_superuser=True))

    response = client.get(reverse("v1:admin-dashboard"))

    assert response.status_code == 401
