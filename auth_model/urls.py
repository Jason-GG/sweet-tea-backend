from django.urls import path

from .views import (
    AccountUpdateView,
    GitHubWebhookView,
    PrInfoView,
    RegisterView,
    RequestEmailVerificationCodeView,
    VerifyEmailCodeView,
    health_check,
)

urlpatterns = [
    # Health check endpoint.
    path("health/", health_check, name="health_check"),
    # GitHub delivers all repository events to this URL.
    path("webhook/", GitHubWebhookView.as_view(), name="github_webhook"),
    # Fetch PR diff and check-run results.
    path("pr-info/", PrInfoView.as_view(), name="github_pr_info"),
    # Email verification + account registration.
    path("auth/request-code/", RequestEmailVerificationCodeView.as_view(), name="request_email_verification_code"),
    path("auth/verify-code/", VerifyEmailCodeView.as_view(), name="verify_email_code"),
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/account/update/", AccountUpdateView.as_view(), name="account_update"),
]
