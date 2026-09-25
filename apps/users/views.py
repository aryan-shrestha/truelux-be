from typing import Any, cast

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.users.models import User
from apps.users.serializers import LogoutSerializer, StaffUserSerializer
from apps.users.services import revoke_refresh_token

AUTH_THROTTLE_SCOPE = "auth"


class StaffTokenObtainView(TokenObtainPairView):
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = AUTH_THROTTLE_SCOPE


class StaffTokenRefreshView(TokenRefreshView):
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = AUTH_THROTTLE_SCOPE


class LogoutView(APIView):
    authentication_classes = (JWTAuthentication,)
    permission_classes = (IsAuthenticated, IsAdminUser)

    @extend_schema(request=LogoutSerializer, responses={204: None})
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        revoke_refresh_token(
            user=cast(User, request.user),
            refresh=serializer.validated_data["refresh"],
        )

        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    authentication_classes = (JWTAuthentication,)
    permission_classes = (IsAuthenticated, IsAdminUser)

    @extend_schema(responses={200: StaffUserSerializer})
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(StaffUserSerializer(cast(User, request.user)).data)
