"""
Django views for GitHub webhook events.

Endpoints
---------
POST /github/api/webhook/
    Webhook called by GitHub to deliver repository events.
    Verifies the HMAC-SHA256 signature from the X-Hub-Signature-256 header,
    then routes pull_request events to the appropriate action handler.

Supported pull_request actions
-------------------------------
    opened       – A new PR was opened.
    closed       – A PR was closed (check pr["merged"] for merge vs plain close).
    reopened     – A previously closed PR was reopened.
    synchronize  – New commits were pushed to the PR branch.
    edited       – PR title/body/base branch was changed.
    labeled      – A label was added to the PR.
    unlabeled    – A label was removed from the PR.
    review_requested        – A reviewer was requested.
    review_request_removed  – A reviewer request was removed.
    assigned     – An assignee was added.
    unassigned   – An assignee was removed.
    ready_for_review        – Draft PR marked as ready.
    converted_to_draft      – PR converted to draft.
    auto_merge_enabled      – Auto-merge was enabled.
    auto_merge_disabled     – Auto-merge was disabled.

Configuration (settings.py)
----------------------------
    GITHUB_WEBHOOK_SECRET  – (str) Shared secret configured in the GitHub webhook
                             settings. Required for signature verification.
                             Set to an empty string or omit to skip verification
                             (not recommended for production).
"""

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from .auth_data import dealing_reopo_func, get_pr_check_runs, get_pr_diff_repo_number
logger = logging.getLogger(__name__)


def _verify_github_signature(request) -> bool:
    """
    Verify the X-Hub-Signature-256 header sent by GitHub.

    Returns True when the signature is valid (or when no secret is configured).
    Returns False when the header is missing or the HMAC does not match.
    """
    secret: str = getattr(settings, "GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        logger.warning(
            "GITHUB_WEBHOOK_SECRET is not set — skipping signature verification. "
            "This is insecure in production."
        )
        return True

    signature_header = request.headers.get("X-Hub-Signature-256", "")
    if not signature_header.startswith("sha256="):
        logger.warning("GitHub webhook: missing or malformed X-Hub-Signature-256 header")
        return False

    expected_sig = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        request.body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, signature_header):
        logger.warning("GitHub webhook: signature mismatch — possible spoofed request")
        return False

    return True


# ---------------------------------------------------------------------------
# PR info API
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name="dispatch")
class PrInfoView(View):
    """
    GET /github/api/pr-info/?repo=owner/repo&pr=<number>

    Returns the raw diff and check-run results for a given PR.
    Requires GITHUB_TOKEN to be set in settings.
    """

    def get(self, request):
        repo_full_name = request.GET.get("repo", "").strip()
        pr_number_str = request.GET.get("pr", "").strip()

        if not repo_full_name or not pr_number_str:
            return JsonResponse({"error": "'repo' and 'pr' query params are required"}, status=400)

        try:
            pr_number = int(pr_number_str)
        except ValueError:
            return JsonResponse({"error": "'pr' must be an integer"}, status=400)

        # Build diff_url the same way GitHub provides it in webhook payloads
        # diff_url = f"https://github.com/{repo_full_name}/pull/{pr_number}.diff"
        diff_content = get_pr_diff_repo_number(repo_full_name, pr_number)

        # Use provided sha or fetch it from the GitHub API
        head_sha = request.GET.get("sha", "").strip()
        if not head_sha:
            import requests as _requests
            from django.conf import settings as _settings
            token = getattr(_settings, "GITHUB_TOKEN", "")
            headers = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if token:
                headers["Authorization"] = f"Bearer {token}"
            try:
                pr_resp = _requests.get(
                    f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}",
                    headers=headers,
                    timeout=10,
                )
                pr_resp.raise_for_status()
                head_sha = pr_resp.json().get("head", {}).get("sha", "")
            except Exception as exc:
                logger.warning("PrInfoView: failed to fetch head SHA for PR %s: %s", pr_number, exc)

        check_runs = get_pr_check_runs(repo_full_name, head_sha) if head_sha else []

        return JsonResponse({
            "repo": repo_full_name,
            "pr": pr_number,
            "diff": diff_content,
            "check_runs": [
                {
                    "name": cr.get("name", ""),
                    "status": cr.get("status", ""),
                    "conclusion": cr.get("conclusion") or "in_progress",
                    "url": cr.get("html_url", ""),
                }
                for cr in check_runs
            ],
        })


# ---------------------------------------------------------------------------
# Pull-request action handlers
# ---------------------------------------------------------------------------

def _handle_pr_opened(pr: dict, repo: dict) -> None:
    logger.info(
        "PR #%s opened in %s by %s: %s",
        pr["number"],
        repo["full_name"],
        pr["user"]["login"],
        pr["title"],
    )
    # logger.info("PR #%s details: %s", pr["number"], pr)
    # judge the repo and PR title/description to decide whether to trigger CI, assign reviewers, etc.
    # repo_name = repo.get("name", "")
    # if repo_name == "linux_inventories":
    # logger.info("PR #%s in %s matches criteria for CI trigger", pr["number"], repo["full_name"])
    dealing_reopo_func(pr, repo)


def _handle_pr_closed(pr: dict, repo: dict) -> None:
    if pr.get("merged"):
        logger.info(
            "PR #%s merged into %s in %s by %s",
            pr["number"],
            pr["base"]["ref"],
            repo["full_name"],
            pr.get("merged_by", {}).get("login", "unknown"),
        )
    else:
        logger.info(
            "PR #%s closed (not merged) in %s",
            pr["number"],
            repo["full_name"],
        )


def _handle_pr_synchronize(pr: dict, repo: dict) -> None:
    logger.info(
        "PR #%s in %s was updated with new commits (head SHA: %s)",
        pr["number"],
        repo["full_name"],
        pr["head"]["sha"],
    )


def _handle_pr_review_requested(pr: dict, repo: dict, payload: dict) -> None:
    requested_reviewer = payload.get("requested_reviewer") or {}
    logger.info(
        "PR #%s in %s: review requested from %s",
        pr["number"],
        repo["full_name"],
        requested_reviewer.get("login", "unknown"),
    )


# Map action strings to handler callables.
# Handlers that need the full payload receive it via **kwargs.
_PR_ACTION_HANDLERS = {
    "opened": lambda pr, repo, payload: _handle_pr_opened(pr, repo),
    "closed": lambda pr, repo, payload: _handle_pr_closed(pr, repo),
    "reopened": lambda pr, repo, payload: _handle_pr_opened(pr, repo),
    "synchronize": lambda pr, repo, payload: _handle_pr_synchronize(pr, repo),
    "review_requested": lambda pr, repo, payload: _handle_pr_review_requested(pr, repo, payload),
}


def _process_pull_request_event(payload: dict) -> None:
    """Route a pull_request event payload to the appropriate action handler."""
    action: str = payload.get("action", "")
    pr: dict = payload.get("pull_request", {})
    repo: dict = payload.get("repository", {})

    logger.info(
        "GitHub pull_request event: action=%s PR#%s repo=%s",
        action,
        pr.get("number"),
        repo.get("full_name"),
    )

    handler = _PR_ACTION_HANDLERS.get(action)
    if handler:
        handler(pr, repo, payload)
    else:
        logger.debug("GitHub pull_request: unhandled action '%s'", action)


# ---------------------------------------------------------------------------
# Webhook view
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name="dispatch")
class GitHubWebhookView(View):
    """
    Receives and processes GitHub webhook payloads.

    GitHub sends a POST request for each subscribed event.
    The X-GitHub-Event header identifies the event type.
    Only pull_request events are processed; all others are acknowledged
    with 200 and ignored.
    """

    def post(self, request):
        # 1. Verify signature.
        if not _verify_github_signature(request):
            return HttpResponse(status=403)

        # 2. Parse body.
        try:
            payload = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            logger.warning("GitHub webhook: invalid JSON body")
            return HttpResponse(status=400)

        # 3. Route by event type.
        event_type = request.headers.get("X-GitHub-Event", "")
        logger.debug("GitHub webhook: received event '%s'", event_type)

        if event_type == "ping":
            logger.info("GitHub webhook: ping received — zen: %s", payload.get("zen", ""))
            return JsonResponse({"message": "pong"}, status=200)

        if event_type == "pull_request":
            try:
                _process_pull_request_event(payload)
            except Exception as exc:
                logger.error(
                    "GitHub webhook: error processing pull_request event: %s",
                    exc,
                    exc_info=True,
                )
                return HttpResponse(status=500)
            return JsonResponse({"message": "pull_request event processed"}, status=200)

        # Acknowledge unhandled event types gracefully.
        logger.debug("GitHub webhook: event '%s' not handled — ignoring", event_type)
        return JsonResponse({"message": f"event '{event_type}' not handled"}, status=200)



def health_check(request):
    """Simple health check endpoint."""
    return JsonResponse({"status": "ok"})