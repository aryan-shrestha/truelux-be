from typing import Any

from django.core.cache import cache
from django.db import connections
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.logging import get_logger

logger = get_logger(__name__)

READINESS_CACHE_KEY = "v1:health:readiness"


class LivenessView(APIView):
    authentication_classes: list[type[Any]] = []
    permission_classes = (AllowAny,)
    throttle_classes: list[type[Any]] = []
    # Health checks sit outside the versioned tree, so NamespaceVersioning would
    # reject their "health" namespace as an unknown API version.
    versioning_class = None

    @extend_schema(
        operation_id="health_live",
        summary="Liveness probe",
        description=(
            "Returns 200 whenever the process can answer requests. Touches no "
            "dependency, so a database outage does not cause healthy containers to "
            "be recycled."
        ),
        responses={200: dict},
        tags=["health"],
    )
    def get(self, request: Request) -> Response:
        return Response({"status": "ok"})


class ReadinessView(APIView):
    authentication_classes: list[type[Any]] = []
    permission_classes = (AllowAny,)
    throttle_classes: list[type[Any]] = []
    versioning_class = None

    @extend_schema(
        operation_id="health_ready",
        summary="Readiness probe",
        description=(
            "Checks the database and the database cache table. Returns 503 naming the "
            "failed check, without exception detail, since the endpoint is unauthenticated."
        ),
        responses={200: dict, 503: dict},
        tags=["health"],
    )
    def get(self, request: Request) -> Response:
        checks = {"database": self._check_database(), "cache": self._check_cache()}
        ready = all(result == "ok" for result in checks.values())

        return Response(
            {"status": "ready" if ready else "not_ready", "checks": checks},
            status=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    def _check_database(self) -> str:
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            logger.exception("health.database_unreachable")
            return "error"
        return "ok"

    def _check_cache(self) -> str:
        try:
            cache.set(READINESS_CACHE_KEY, "1", timeout=10)
            if cache.get(READINESS_CACHE_KEY) != "1":
                logger.error("health.cache_roundtrip_failed")
                return "error"
        # A probe reports failure and must never raise. The cache is a table that only
        # exists if the build ran `createcachetable` (ADR 0014), so this catches that.
        except Exception:
            logger.exception("health.cache_unreachable")
            return "error"
        return "ok"
