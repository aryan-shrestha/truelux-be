from typing import Any

from django.conf import settings
from django.core.cache import caches
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle, UserRateThrottle

from apps.core.logging import get_logger

logger = get_logger(__name__)


class PerProcessFallbackThrottleMixin:
    """Counts in-process when the shared throttle backend is unreachable.

    DRF's throttles let a cache error propagate, which turns a Redis outage into a
    500 on every endpoint, because the throttle runs before the view. Falling back
    to a local cache keeps the limit enforced per worker instead: the effective
    limit multiplies by the worker count, which is the degradation
    `docs/architecture.md` describes, rather than no limit at all.
    """

    cache: Any

    def allow_request(self, request: Any, view: Any) -> bool:
        try:
            return bool(super().allow_request(request, view))  # type: ignore[misc]  # mixin has no base
        except Exception:  # noqa: BLE001  # any backend failure degrades, never 500s
            logger.warning("throttle.backend_unavailable", scope=getattr(self, "scope", None))
            return self._allow_request_in_process(request, view)

    def _allow_request_in_process(self, request: Any, view: Any) -> bool:
        # No second guard here: the fallback is in-memory and cannot fail for the
        # reasons the shared backend does, so an error at this point is a bug and
        # should surface rather than silently disable throttling.
        shared_cache = self.cache
        self.cache = caches[settings.THROTTLE_FALLBACK_CACHE_ALIAS]
        try:
            return bool(super().allow_request(request, view))  # type: ignore[misc]  # mixin has no base
        finally:
            self.cache = shared_cache


class ResilientAnonRateThrottle(PerProcessFallbackThrottleMixin, AnonRateThrottle):
    pass


class ResilientUserRateThrottle(PerProcessFallbackThrottleMixin, UserRateThrottle):
    pass


class ResilientScopedRateThrottle(PerProcessFallbackThrottleMixin, ScopedRateThrottle):
    pass
