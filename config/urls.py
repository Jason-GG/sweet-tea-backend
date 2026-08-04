"""URL configuration for GitHub Project."""

from django.urls import path, include

urlpatterns = [
    path("github/api/", include("github.urls")),
]
