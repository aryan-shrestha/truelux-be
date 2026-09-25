from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

# The "v1" namespace is what NamespaceVersioning reads to resolve request.version,
# so route names are namespaced: reverse("v1:product-list").
api_v1_patterns: list[URLPattern | URLResolver] = [
    path("", include("apps.users.urls")),
    path("", include("apps.catalog.urls")),
    path("", include("apps.orders.urls")),
]

urlpatterns = [
    # Not /admin/, so the Django admin is never confused with the TrueLux admin app.
    path("django-admin/", admin.site.urls),
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

# An empty list unless DEBUG; in production uploads are served by Cloudinary's CDN.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
