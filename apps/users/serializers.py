from rest_framework import serializers

from apps.users.models import User


class StaffUserSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name")


class LogoutSerializer(serializers.Serializer[None]):
    refresh = serializers.CharField()
