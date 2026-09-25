"""Root URL configuration.

Versioned API routes live under ``/api/v1/`` in the ``v1`` namespace, which is what
``NamespaceVersioning`` reads to resolve ``request.version``. Route names are
therefore namespaced: ``reverse("v1:product-list")``. ``users`` registers nothing
here, being admin-only by design.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

api_v1_patterns: list[URLPattern | URLResolver] = [
    path("", include("apps.catalog.urls")),
    path("", include("apps.orders.urls")),
    path("", include("apps.payments.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", include("apps.core.urls")),
    path("api/v1/", include((api_v1_patterns, "v1"), namespace="v1")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("api/schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

# Returns an empty list unless DEBUG. In production uploads live on Cloudinary and
# are served from its CDN, so nothing here ever serves an uploaded file.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
