from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.catalog.views import CategoryListView, ProductViewSet

# SimpleRouter, not DefaultRouter: the latter adds an API-root view that this
# feature does not publish.
router = SimpleRouter()
router.register("products", ProductViewSet, basename="product")

urlpatterns = [
    path("categories/", CategoryListView.as_view(), name="category-list"),
    *router.urls,
]
