from django.urls import path

from .views import (
    DriverDetailView,
    DriverListCreateView,
    DriverArchiveView,
    ArchivedDriverListView,
    DriverPhotoView,
    DriverRestoreView,
    DriverStatsView,
    DriverStatusView,
    DriverUniqueCheckView,
)

app_name = "drivers"

urlpatterns = [
    path("", DriverListCreateView.as_view(), name="list"),
    path("archived/", ArchivedDriverListView.as_view(), name="archived"),
    path("stats/", DriverStatsView.as_view(), name="stats"),
    path("check-unique/", DriverUniqueCheckView.as_view(), name="check-unique"),
    path("<int:pk>/archive/", DriverArchiveView.as_view(), name="archive"),
    path("<int:pk>/restore/", DriverRestoreView.as_view(), name="restore"),
    path("<int:pk>/", DriverDetailView.as_view(), name="detail"),
    path("<int:pk>/photo/", DriverPhotoView.as_view(), name="photo"),
    path("<int:pk>/status/", DriverStatusView.as_view(), name="status"),
]
