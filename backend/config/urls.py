"""Root URL configuration for the Driver Management System."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.core.urls")),
    path("api/", include("apps.payments.urls")),
    path("api/drivers/", include("apps.drivers.urls")),
    path("api/documents/", include("apps.documents.urls")),
]

# Media files are deliberately not exposed through MEDIA_URL. Driver photos are
# streamed by the authenticated /api/drivers/<id>/photo/ endpoint instead.
