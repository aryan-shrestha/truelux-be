import pytest
from django.urls import reverse

from apps.users.models import User
from apps.users.tests.factories import UserFactory


@pytest.fixture
def admin_client(client):
    staff = UserFactory(is_staff=True, is_superuser=True)
    client.force_login(staff)
    return client


@pytest.mark.django_db
def test_changelist_renders(admin_client):
    response = admin_client.get(reverse("admin:users_user_changelist"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_add_form_renders(admin_client):
    response = admin_client.get(reverse("admin:users_user_add"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_creating_a_user_through_the_admin_hashes_the_password(admin_client):
    response = admin_client.post(
        reverse("admin:users_user_add"),
        {
            "email": "new-staff@example.com",
            "password1": "an-adequately-long-password",
            "password2": "an-adequately-long-password",
            "usable_password": "true",
            # The Profile inline's management form; a browser submits these.
            "profile-TOTAL_FORMS": "1",
            "profile-INITIAL_FORMS": "0",
            "profile-MIN_NUM_FORMS": "0",
            "profile-MAX_NUM_FORMS": "1",
            "profile-0-display_name": "New Staff",
        },
    )

    assert response.status_code == 302
    created = User.objects.get(email="new-staff@example.com")
    assert created.check_password("an-adequately-long-password")
    assert created.profile.display_name == "New Staff"


@pytest.mark.django_db
def test_change_form_renders_for_an_existing_user(admin_client):
    user = UserFactory()

    response = admin_client.get(reverse("admin:users_user_change", args=[user.pk]))

    assert response.status_code == 200


def test_the_django_admin_is_mounted_away_from_admin():
    assert reverse("admin:index") == "/django-admin/"
