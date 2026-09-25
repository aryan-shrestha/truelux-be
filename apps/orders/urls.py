from django.urls import path

from apps.orders.views import CheckoutView, OrderDetailView, OrderLookupView

urlpatterns = [
    path("checkout/", CheckoutView.as_view(), name="checkout"),
    path("orders/lookup/", OrderLookupView.as_view(), name="order-lookup"),
    path("orders/<uuid:access_token>/", OrderDetailView.as_view(), name="order-detail"),
]
