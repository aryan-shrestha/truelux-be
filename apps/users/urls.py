from django.urls import path

from apps.users.views import LogoutView, MeView, StaffTokenObtainView, StaffTokenRefreshView

urlpatterns = [
    path("auth/token/", StaffTokenObtainView.as_view(), name="auth-token"),
    path("auth/token/refresh/", StaffTokenRefreshView.as_view(), name="auth-token-refresh"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
]
