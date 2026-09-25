from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.core.permissions import IsOwnerOrAdmin
from apps.users.tests.factories import UserFactory


def _request(user):
    request = APIRequestFactory().get("/")
    request.user = user
    return request


@pytest.mark.django_db
def test_owner_is_allowed():
    owner = UserFactory()
    obj = SimpleNamespace(user=owner)

    assert IsOwnerOrAdmin().has_object_permission(_request(owner), APIView(), obj)


@pytest.mark.django_db
def test_another_user_is_denied():
    obj = SimpleNamespace(user=UserFactory())

    assert not IsOwnerOrAdmin().has_object_permission(_request(UserFactory()), APIView(), obj)


@pytest.mark.django_db
def test_staff_is_allowed_regardless_of_ownership():
    staff = UserFactory(is_staff=True)
    obj = SimpleNamespace(user=UserFactory())

    assert IsOwnerOrAdmin().has_object_permission(_request(staff), APIView(), obj)
