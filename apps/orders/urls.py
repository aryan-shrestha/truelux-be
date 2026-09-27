from django.urls import path

from apps.orders.views import (
    CheckoutView,
    OrderDetailView,
    OrderLookupView,
    QuoteView,
    ShippingSettingsView,
)

urlpatterns = [
    path("checkout/", CheckoutView.as_view(), name="checkout"),
    path("checkout/quote/", QuoteView.as_view(), name="checkout-quote"),
    path("shipping/", ShippingSettingsView.as_view(), name="shipping"),
    path("orders/lookup/", OrderLookupView.as_view(), name="order-lookup"),
    path("orders/<uuid:access_token>/", OrderDetailView.as_view(), name="order-detail"),
]
