from unittest import mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from rest_framework.throttling import SimpleRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-battery"


@pytest.fixture
def staff():
    user = UserFactory(email="staff@truelux.com", is_staff=True, first_name="Asha", last_name="Rai")
    user.set_password(PASSWORD)
    user.save()
    return user


def _login(api_client, email, password=PASSWORD):
    return api_client.post(reverse("v1:auth-token"), {"email": email, "password": password})


def _bearer(api_client, user):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return api_client


def test_staff_login_returns_an_access_and_refresh_token(api_client, staff):
    response = _login(api_client, "staff@truelux.com")

    assert response.status_code == 200
    assert set(response.data) == {"access", "refresh"}


def test_every_failed_login_returns_the_same_401(api_client, staff):
    customer = UserFactory(email="customer@truelux.com")
    customer.set_password(PASSWORD)
    customer.save()
    inactive = UserFactory(email="gone@truelux.com", is_staff=True, is_active=False)
    inactive.set_password(PASSWORD)
    inactive.save()

    responses = [
        _login(api_client, "staff@truelux.com", "wrong-password"),
        _login(api_client, "nobody@truelux.com"),
        _login(api_client, "gone@truelux.com"),
        _login(api_client, "customer@truelux.com"),
    ]

    assert {response.status_code for response in responses} == {401}
    assert len({response.content for response in responses}) == 1
    assert responses[0].data["error"]["code"] == "authentication_failed"


def test_refresh_rotates_and_the_old_token_cannot_be_reused(api_client, staff):
    old_refresh = _login(api_client, "staff@truelux.com").data["refresh"]

    rotated = api_client.post(reverse("v1:auth-token-refresh"), {"refresh": old_refresh})
    reused = api_client.post(reverse("v1:auth-token-refresh"), {"refresh": old_refresh})

    assert rotated.status_code == 200
    assert set(rotated.data) == {"access", "refresh"}
    assert rotated.data["refresh"] != old_refresh
    assert reused.status_code == 401
    assert reused.data["error"]["code"] == "authentication_failed"


def test_refresh_fails_once_the_user_loses_staff_rights(api_client, staff):
    refresh = _login(api_client, "staff@truelux.com").data["refresh"]
    User.objects.filter(pk=staff.pk).update(is_staff=False)

    response = api_client.post(reverse("v1:auth-token-refresh"), {"refresh": refresh})

    assert response.status_code == 401
    assert response.data["error"]["code"] == "authentication_failed"


def test_logout_blacklists_the_refresh_token(api_client, staff):
    refresh = _login(api_client, "staff@truelux.com").data["refresh"]

    logout = _bearer(api_client, staff).post(reverse("v1:auth-logout"), {"refresh": refresh})
    refreshed = api_client.post(reverse("v1:auth-token-refresh"), {"refresh": refresh})

    assert logout.status_code == 204
    assert refreshed.status_code == 401


def test_logout_rejects_another_users_refresh_token(api_client, staff):
    other = UserFactory.create(is_staff=True)

    response = _bearer(api_client, staff).post(
        reverse("v1:auth-logout"), {"refresh": str(RefreshToken.for_user(other))}
    )

    assert response.status_code == 422
    assert response.data["error"]["code"] == "invalid_refresh_token"


def test_logout_requires_a_token(api_client):
    response = api_client.post(reverse("v1:auth-logout"), {"refresh": "x"})

    assert response.status_code == 401


def test_me_returns_the_signed_in_staff_user(api_client, staff):
    response = _bearer(api_client, staff).get(reverse("v1:auth-me"))

    assert response.status_code == 200
    assert response.data == {
        "id": str(staff.pk),
        "email": "staff@truelux.com",
        "first_name": "Asha",
        "last_name": "Rai",
    }


def test_me_requires_a_token(api_client):
    response = api_client.get(reverse("v1:auth-me"))

    assert response.status_code == 401
    assert response.data["error"]["code"] == "authentication_failed"


def test_me_is_forbidden_to_a_non_staff_token(api_client):
    response = _bearer(api_client, UserFactory()).get(reverse("v1:auth-me"))

    assert response.status_code == 403
    assert response.data["error"]["code"] == "permission_denied"


def test_me_ignores_a_django_admin_session(client, staff):
    client.force_login(staff)

    response = client.get(reverse("v1:auth-me"))

    assert response.status_code == 401


def test_exceeding_the_auth_throttle_returns_429(api_client, staff):
    with mock.patch.object(
        SimpleRateThrottle,
        "THROTTLE_RATES",
        {**SimpleRateThrottle.THROTTLE_RATES, "auth": "2/minute"},
    ):
        statuses = [_login(api_client, "staff@truelux.com", "wrong").status_code for _ in range(3)]

    assert statuses == [401, 401, 429]


def test_seed_staff_creates_a_staff_user_that_can_log_in(api_client, settings):
    settings.DEBUG = True

    call_command("seed_staff")
    call_command("seed_staff")

    user = User.objects.get(email=settings.DEMO_STAFF_EMAIL)
    assert user.is_staff
    response = _login(api_client, settings.DEMO_STAFF_EMAIL, settings.DEMO_STAFF_PASSWORD)
    assert response.status_code == 200


def test_seed_staff_refuses_outside_debug(settings):
    settings.DEBUG = False

    with pytest.raises(CommandError, match="DEBUG"):
        call_command("seed_staff")

    assert not User.objects.exists()


def test_seed_staff_deploy_creates_a_staff_login_outside_debug(api_client, settings):
    settings.DEBUG = False
    settings.SEED_DEMO_DATA = True

    call_command("seed_staff", "--deploy")

    assert User.objects.get(email=settings.DEMO_STAFF_EMAIL).is_staff
    response = _login(api_client, settings.DEMO_STAFF_EMAIL, settings.DEMO_STAFF_PASSWORD)
    assert response.status_code == 200


def test_seed_staff_deploy_is_a_no_op_while_seed_demo_data_is_false(settings):
    settings.DEBUG = False
    settings.SEED_DEMO_DATA = False

    call_command("seed_staff", "--deploy")

    assert not User.objects.exists()


def test_seed_staff_deploy_never_resets_an_existing_password(api_client, settings):
    settings.DEBUG = False
    settings.SEED_DEMO_DATA = True
    user = UserFactory(email=settings.DEMO_STAFF_EMAIL, is_staff=True)
    user.set_password(PASSWORD)
    user.save()

    call_command("seed_staff", "--deploy")

    assert User.objects.count() == 1
    assert _login(api_client, settings.DEMO_STAFF_EMAIL).status_code == 200


def test_seed_staff_deploy_rejects_a_short_password(settings):
    settings.DEBUG = False
    settings.SEED_DEMO_DATA = True
    settings.DEMO_STAFF_PASSWORD = "elevenchars"

    with pytest.raises(CommandError, match="12 characters"):
        call_command("seed_staff", "--deploy")

    assert not User.objects.exists()
