import logging

import requests
from django.conf import settings

"""External integrations for MailerSend and GitHub repository data.

This module keeps outbound HTTP integrations in one place so views can call a
small, testable API.
"""
logger = logging.getLogger(__name__)


def send_email(to_email: str, code: str, to_name: str | None = None) -> dict:
    """Send an email verification code using MailerSend."""
    access_token = getattr(settings, "MAILERSEND_API_TOKEN", "")
    mail_url = getattr(settings, "MAILERSEND_API_URL", "https://api.mailersend.com/v1/email")
    from_email = getattr(settings, "MAILERSEND_FROM_EMAIL", "MS_peZn6j@test-2p0347zee5klzdrn.mlsender.net")
    from_name = getattr(settings, "MAILERSEND_FROM_NAME", "Sweet Tea")

    if not access_token or not from_email:
        raise RuntimeError("MAILERSEND_API_TOKEN and MAILERSEND_FROM_EMAIL must be configured")

    display_name = to_name or to_email
    payload = {
        "from": {
            "email": from_email,
            "name": from_name,
        },
        "to": [
            {
                "email": to_email,
                "name": display_name,
            }
        ],
        "subject": "Your Sweet Tea verification code",
        "text": f"Your Sweet Tea verification code is {code}. It expires soon.",
        "html": f"<p>Your Sweet Tea verification code is <b>{code}</b>.</p><p>It expires soon.</p>",
        "personalization": [
            {
                "email": to_email,
                "data": {
                    "code": code,
                },
            }
        ],
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
    }
    result = requests.post(mail_url, json=payload, headers=headers, timeout=10)
    result.raise_for_status()
    if result.content:
        try:
            return result.json()
        except ValueError:
            logger.debug("MailerSend returned non-JSON response: %s", result.text)
    return {"status_code": result.status_code}


def _github_headers() -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = getattr(settings, "GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def get_pr_diff_repo_number(repo_full_name: str, pr_number: int | str) -> str:
    """Fetch the diff for a pull request from GitHub."""
    headers = _github_headers()
    headers["Accept"] = "application/vnd.github.v3.diff"
    response = requests.get(
        f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}",
        headers=headers,
        timeout=15,
    )
    response.raise_for_status()
    return response.text


def get_pr_check_runs(repo_full_name: str, head_sha: str) -> list[dict]:
    """Fetch check runs for a pull request head SHA from GitHub."""
    response = requests.get(
        f"https://api.github.com/repos/{repo_full_name}/commits/{head_sha}/check-runs",
        headers=_github_headers(),
        timeout=15,
    )
    response.raise_for_status()
    return response.json().get("check_runs", [])


def dealing_reopo_func(pr: dict, repo: dict) -> None:
    """Placeholder for repository-specific PR business logic."""
    logger.info("Received PR #%s for repository %s", pr.get("number"), repo.get("full_name"))



if __name__ == "__main__":
    raise SystemExit("send_email requires Django settings and recipient arguments")
