from django.urls import path

from apps.backoffice import views

urlpatterns = [
    path("dashboard/", views.DashboardView.as_view(), name="admin-dashboard"),
    path("products/", views.ProductListView.as_view(), name="admin-product-list"),
    path(
        "products/<uuid:product_id>/",
        views.ProductDetailView.as_view(),
        name="admin-product-detail",
    ),
    path(
        "products/<uuid:product_id>/variants/",
        views.ProductVariantCreateView.as_view(),
        name="admin-product-variants",
    ),
    path(
        "products/<uuid:product_id>/images/",
        views.ProductImageCreateView.as_view(),
        name="admin-product-images",
    ),
    path(
        "variants/<uuid:variant_id>/",
        views.VariantDetailView.as_view(),
        name="admin-variant-detail",
    ),
    path("images/<uuid:image_id>/", views.ImageDetailView.as_view(), name="admin-image-detail"),
    path("brands/", views.BrandListView.as_view(), name="admin-brand-list"),
    path("brands/<uuid:entry_id>/", views.BrandDetailView.as_view(), name="admin-brand-detail"),
    path("categories/", views.CategoryListView.as_view(), name="admin-category-list"),
    path(
        "categories/<uuid:entry_id>/",
        views.CategoryDetailView.as_view(),
        name="admin-category-detail",
    ),
    path("shades/", views.ShadeListView.as_view(), name="admin-shade-list"),
    path("shades/<uuid:entry_id>/", views.ShadeDetailView.as_view(), name="admin-shade-detail"),
    path("sizes/", views.SizeListView.as_view(), name="admin-size-list"),
    path("sizes/<uuid:entry_id>/", views.SizeDetailView.as_view(), name="admin-size-detail"),
    path("skin-types/", views.SkinTypeListView.as_view(), name="admin-skin-type-list"),
    path(
        "skin-types/<uuid:entry_id>/",
        views.SkinTypeDetailView.as_view(),
        name="admin-skin-type-detail",
    ),
    path("orders/", views.OrderListView.as_view(), name="admin-order-list"),
    path("orders/<uuid:order_id>/", views.OrderDetailView.as_view(), name="admin-order-detail"),
    path(
        "orders/<uuid:order_id>/transition/",
        views.OrderTransitionView.as_view(),
        name="admin-order-transition",
    ),
    path(
        "settings/shipping/",
        views.ShippingSettingsView.as_view(),
        name="admin-shipping-settings",
    ),
]
