from datetime import UTC, datetime

import pytest
from django.db import IntegrityError
from freezegun import freeze_time

from apps.users.models import User
from apps.users.tests.factories import ProfileFactory, UserFactory


@pytest.mark.django_db
def test_create_user_normalises_email_domain_and_hashes_password():
    user = User.objects.create_user(email="Person@EXAMPLE.COM", password="s3cret-pw")

    assert user.email == "Person@example.com"
    assert user.password != "s3cret-pw"
    assert user.check_password("s3cret-pw")


@pytest.mark.django_db
def test_create_user_without_email_raises_value_error():
    with pytest.raises(ValueError, match="email address"):
        User.objects.create_user(email="", password="s3cret-pw")


@pytest.mark.django_db
def test_create_superuser_sets_staff_and_superuser_flags():
    user = User.objects.create_superuser(email="boss@example.com", password="s3cret-pw")

    assert user.is_staff
    assert user.is_superuser


@pytest.mark.django_db
def test_create_superuser_without_staff_flag_raises_value_error():
    with pytest.raises(ValueError, match="is_staff=True"):
        User.objects.create_superuser(
            email="boss@example.com", password="s3cret-pw", is_staff=False
        )


@pytest.mark.django_db
def test_duplicate_email_violates_unique_constraint():
    UserFactory(email="taken@example.com")

    with pytest.raises(IntegrityError):
        UserFactory(email="taken@example.com")


@pytest.mark.django_db
def test_empty_email_violates_check_constraint():
    with pytest.raises(IntegrityError):
        User.objects.create(email="")


@pytest.mark.django_db
def test_user_id_is_a_uuid_assigned_before_insert():
    user = UserFactory.build()

    assert user.pk is not None
    assert user.pk.version == 4


@pytest.mark.django_db
def test_updated_at_advances_on_save_while_created_at_holds():
    with freeze_time("2026-01-01 00:00:00"):
        user = UserFactory()
        created_at = user.created_at

    with freeze_time("2026-06-01 12:00:00"):
        user.first_name = "Renamed"
        user.save(update_fields=["first_name", "updated_at"])

    user.refresh_from_db()

    assert user.created_at == created_at
    assert user.updated_at > created_at
    assert user.updated_at == datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


@pytest.mark.django_db
def test_deleting_a_user_cascades_to_their_profile():
    profile = ProfileFactory()
    user = profile.user

    user.delete()

    assert not type(profile).objects.filter(pk=profile.pk).exists()


@pytest.mark.django_db
def test_profile_str_falls_back_to_user_email_when_unnamed():
    profile = ProfileFactory(display_name="")

    assert str(profile) == profile.user.email
