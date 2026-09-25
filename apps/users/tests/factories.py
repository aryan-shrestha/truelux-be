import factory
from factory.django import DjangoModelFactory

from apps.users.models import Profile, User


class UserFactory(DjangoModelFactory[User]):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")


class ProfileFactory(DjangoModelFactory[Profile]):
    class Meta:
        model = Profile

    user = factory.SubFactory(UserFactory)
