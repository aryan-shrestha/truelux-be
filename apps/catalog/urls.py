from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.catalog.views import (
    BrandViewSet,
    CategoryListView,
    ProductViewSet,
    ShadeListView,
    SizeListView,
)

# SimpleRouter: DefaultRouter adds an API-root view this API does not publish.
router = SimpleRouter()
router.register("products", ProductViewSet, basename="product")
router.register("brands", BrandViewSet, basename="brand")

urlpatterns = [
    path("categories/", CategoryListView.as_view(), name="category-list"),
    path("shades/", ShadeListView.as_view(), name="shade-list"),
    path("sizes/", SizeListView.as_view(), name="size-list"),
    *router.urls,
]
