from unittest import mock

import pytest
from rest_framework.test import APIClient

from apps.payments.tests.khalti_stubs import INITIATE_BODY, FakeResponse
from apps.users.tests.factories import UserFactory


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def khalti_post():
    """Stubs the one place this system talks to Khalti. No test reaches the network.

    Shared rather than per-package: the checkout tests in `apps/orders` need it as
    much as the payment tests do.
    """
    with mock.patch("apps.payments.client.requests.post") as post:
        post.return_value = FakeResponse(INITIATE_BODY)
        yield post
