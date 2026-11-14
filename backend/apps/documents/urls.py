from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path("upload/", views.DocumentUploadView.as_view(), name="upload"),
    path("", views.DocumentListView.as_view(), name="list"),
    path("<int:pk>/download/", views.DocumentDownloadView.as_view(), name="download"),
    path("<int:pk>/deactivate/", views.DocumentDeactivateView.as_view(), name="deactivate"),
]