from django.urls import path

from .views import GitHubWebhookView, PrInfoView, health_check

urlpatterns = [
    # Health check endpoint.
    path("health/", health_check, name="health_check"),
    # GitHub delivers all repository events to this URL.
    path("webhook/", GitHubWebhookView.as_view(), name="github_webhook"),
    # Fetch PR diff and check-run results.
    path("pr-info/", PrInfoView.as_view(), name="github_pr_info"),
]
