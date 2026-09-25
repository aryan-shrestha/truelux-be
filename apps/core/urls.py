from django.urls import path

from apps.core.views import LivenessView, ReadinessView

app_name = "health"

urlpatterns = [
    path("", LivenessView.as_view(), name="live"),
    path("ready/", ReadinessView.as_view(), name="ready"),
]
