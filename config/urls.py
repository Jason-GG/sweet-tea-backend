"""URL configuration for GitHub Project."""

from django.urls import path, include

urlpatterns = [
    path("api/", include("auth_model.urls")),
]
