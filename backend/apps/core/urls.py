from django.urls import path

from .views import (
    ActivityLogDetailView,
    ActivityLogFilterOptionsView,
    ActivityLogListView,
    CsrfView,
    HealthView,
    LoginView,
    LogoutView,
    MeView,
    UserManagementDetailView,
    UserManagementView,
    UserPasswordResetView,
)

app_name = "core"

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("auth/csrf/", CsrfView.as_view(), name="csrf"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("users/", UserManagementView.as_view(), name="user-management"),
    path("users/<int:pk>/", UserManagementDetailView.as_view(), name="user-management-detail"),
    path(
        "users/<int:pk>/password/",
        UserPasswordResetView.as_view(),
        name="user-password-reset",
    ),
    path("activity-logs/", ActivityLogListView.as_view(), name="activity-log-list"),
    path(
        "activity-logs/filters/",
        ActivityLogFilterOptionsView.as_view(),
        name="activity-log-filters",
    ),
    path(
        "activity-logs/<int:pk>/",
        ActivityLogDetailView.as_view(),
        name="activity-log-detail",
    ),
]
