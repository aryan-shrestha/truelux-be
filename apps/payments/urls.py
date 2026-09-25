from django.urls import path

from apps.payments.views import KhaltiReturnView

urlpatterns = [
    path("payments/khalti/return/", KhaltiReturnView.as_view(), name="khalti-return"),
]
