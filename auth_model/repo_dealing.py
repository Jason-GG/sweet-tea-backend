import time
import requests
import logging
from django.conf import settings

"""Module for handling GitHub repository interactions, such as processing pull request events.
This module can be expanded with functions to interact with the GitHub API, manage repository data,and implement business logic related to repository management.
"""
logger = logging.getLogger(__name__)

CMDB_URL = "https://cmdb-api.cloud.microstrategy.com"
DIFF_MAX_LINES = 3000
DIFF_RETRIES = 3
def get_pr_check_runs(repo_full_name: str, head_sha: str) -> list:
    """
    Fetch GitHub Actions check runs for a specific commit SHA via the GitHub API.
    Retries up to 3 times (with 10-second waits) if the result is empty.
    Requires GITHUB_TOKEN with:
      - Classic PAT: 'repo' scope
      - Fine-grained PAT: 'Checks: Read' + repo access
    Falls back to commit statuses (requires 'repo:status' scope) on 403.
    """
    token = getattr(settings, "GITHUB_TOKEN", "")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/repos/{repo_full_name}/commits/{head_sha}/check-runs"

    max_retries = DIFF_RETRIES
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 403 or "sso" in resp.url:
                logger.warning(
                    "403/SSO block fetching check-runs for %s@%s — "
                    "authorize your token for the org SAML SSO at: "
                    "GitHub → Settings → Developer settings → Personal access tokens → Configure SSO → Authorize 'mstr-mce'",
                    repo_full_name, head_sha,
                )
                return _get_commit_statuses(repo_full_name, head_sha, headers)
            resp.raise_for_status()
            check_runs = resp.json().get("check_runs", [])
            if check_runs:
                # Retry if any check run is still in_progress or queued (not yet completed)
                pending = [
                    cr for cr in check_runs
                    if cr.get("status") != "completed"
                ]
                if pending and attempt < max_retries:
                    pending_names = ", ".join(
                        f"{cr.get('name', '')}({cr.get('status', '')})"
                        for cr in pending
                    )
                    logger.info(
                        "get_pr_check_runs: %d check(s) still pending [%s] for %s@%s, retrying (%d/%d) in 10s...",
                        len(pending), pending_names, repo_full_name, head_sha, attempt, max_retries,
                    )
                    time.sleep(10)
                    continue
                return check_runs
            # Empty result — retry after waiting
            if attempt < max_retries:
                logger.info(
                    "get_pr_check_runs: empty result for %s@%s, retrying (%d/%d) in 10s...",
                    repo_full_name, head_sha, attempt, max_retries,
                )
                time.sleep(10)
            else:
                logger.warning(
                    "get_pr_check_runs: no check runs found for %s@%s after %d attempts",
                    repo_full_name, head_sha, max_retries,
                )
                return []
        except Exception as exc:
            logger.warning("Failed to fetch check runs for %s@%s: %s", repo_full_name, head_sha, exc)
            if attempt < max_retries:
                logger.info("Retrying (%d/%d) in 10s...", attempt, max_retries)
                time.sleep(10)
            else:
                return []
    return []


def _get_commit_statuses(repo_full_name: str, head_sha: str, headers: dict) -> list:
    """
    Fallback: fetch commit statuses (requires repo:status scope).
    Returns a list shaped like check-run objects so callers need no changes.
    """
    url = f"https://api.github.com/repos/{repo_full_name}/commits/{head_sha}/statuses"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        statuses = resp.json()
        # Normalise to check-run shape
        return [
            {
                "name": s.get("context", ""),
                "status": "completed",
                "conclusion": s.get("state", ""),  # success / failure / pending / error
                "html_url": s.get("target_url", ""),
            }
            for s in statuses
        ]
    except Exception as exc:
        logger.warning("Failed to fetch commit statuses for %s@%s: %s", repo_full_name, head_sha, exc)
        return []


# def get_pr_diff(diff_url: str) -> str:
#     """
#     Fetch the raw unified diff of a PR via the GitHub API.
#     diff_url is the browser URL (e.g. https://github.com/owner/repo/pull/123.diff)
#     — the PR number and repo are extracted from it and the API endpoint is used instead.
#     """
#     if not diff_url:
#         return ""
#     # Extract repo and PR number from the browser diff URL
#     # e.g. https://github.com/mstr-mce/linux_inventories/pull/6695.diff
#     import re
#     m = re.search(r"github\.com/(.+)/pull/(\d+)", diff_url)
#     if not m:
#         logger.warning("get_pr_diff: could not parse repo/pr from url %s", diff_url)
#         return ""
#     repo_full_name = m.group(1)
#     pr_number = m.group(2)

#     token = getattr(settings, "GITHUB_TOKEN", "")
#     headers = {
#         "Accept": "application/vnd.github.v3.diff",
#         "X-GitHub-Api-Version": "2022-11-28",
#     }
#     if token:
#         headers["Authorization"] = f"Bearer {token}"

#     api_url = f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}"
#     try:
#         resp = requests.get(api_url, headers=headers, timeout=15, allow_redirects=True)
#         logger.info("get_pr_diff: status=%s url=%s", resp.status_code, api_url)
#         if resp.status_code == 403:
#             logger.warning(
#                 "403 fetching diff for %s #%s — check token SSO authorization for the org",
#                 repo_full_name, pr_number,
#             )
#             return ""
#         resp.raise_for_status()
#         content = resp.text
#         if content.lstrip().startswith("<"):
#             logger.warning("get_pr_diff received HTML instead of diff for %s #%s", repo_full_name, pr_number)
#             return ""
#         if len(content) > 3000:
#             content = content[:3000] + "\n... (truncated)"
#         return content
#     except Exception as exc:
#         logger.warning("Failed to fetch diff for %s #%s: %s", repo_full_name, pr_number, exc)
#         return ""

def get_pr_diff_repo_number(repo_full_name: str, pr_number: str) -> str:
    token = getattr(settings, "GITHUB_TOKEN", "")
    headers = {
        "Accept": "application/vnd.github.v3.diff",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    api_url = f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}"
    try:
        resp = requests.get(api_url, headers=headers, timeout=15, allow_redirects=True)
        logger.info("get_pr_diff: status=%s url=%s", resp.status_code, api_url)
        if resp.status_code == 403:
            logger.warning(
                "403 fetching diff for %s #%s — check token SSO authorization for the org",
                repo_full_name, pr_number,
            )
            return ""
        resp.raise_for_status()
        content = resp.text
        if content.lstrip().startswith("<"):
            logger.warning("get_pr_diff received HTML instead of diff for %s #%s", repo_full_name, pr_number)
            return ""
        if len(content) > DIFF_MAX_LINES:
            content = content[:DIFF_MAX_LINES] + "\n... (truncated)"
        return content
    except Exception as exc:
        logger.warning("Failed to fetch diff for %s #%s: %s", repo_full_name, pr_number, exc)
        return ""


def _submit_approval_request(request_payload: dict) -> None:
    """
    Example function to submit PR details to an external workflow engine.
    This is a placeholder for your actual logic to send data to your workflow system.
    """
    # Send this data to your workflow engine
    response = requests.post(
        f"{CMDB_URL}/api/ApprovalRequests",
        json=request_payload,
        headers={"Authorization": "Basic aXRzQG1pY3Jvc3RyYXRlZ3kuY29tOmtAajEyM0M5U1prY3ckUmFzZHMxMiFAIw=="},
    )
    logger.info(f"Workflow engine response: {response.status_code} - {response.text}")
    return response.json()  # Return True if the request was successful, False otherwise


def dealing_reopo_func(pr: dict, repo: dict) -> bool:
    """
    Example function to judge whether a PR in the 'linux_inventories' repo matches certain criteria.
    This is a placeholder for your actual logic to decide if the PR should trigger CI, assign reviewers, etc.
    """
    # logger.info(f"Evaluating PR repo: # {repo}for further processing")
    repo_name = repo.get("name", "")
    # if repo_name == "linux_inventories":
    request_payload = {
        "workflow_config_id": 2,
        "submitted_by": pr.get("user", {}).get("login", ""),
        "name": f"PR #{pr.get('number', '')} - {pr.get('title', '')} - {pr.get('head', {}).get('ref', '')} - <a href=\"{pr.get('html_url', '')}\">{pr.get('html_url', '')}</a>",
        "cloud": repo_name,
        "customer_id": (pr.get("requested_teams") or [{}])[0].get("name", ""),
        "cluster_id": "cluster-abc",
        "environment_id": "env-456",
        "client_impact": "low",
        "security_impact": "none",
        "operational_impact": "medium",
        "impact_notes": f"PR #{pr.get('number', '')} in {repo.get('full_name', '')}",
        "impact_priority": "medium",
        "reason": f"PR #{pr.get('number', '')} opened in {repo.get('full_name', '')}",
        "description": f"PR #{pr.get('number', '')} - {pr.get('title', '')} - {repo.get('full_name', '')} - {pr.get('head', {}).get('ref', '')}",
        "submitted_param": pr,
    }
    # Fetch fresh PR data from GitHub API to get reliable head SHA + check runs + diff
    token = getattr(settings, "GITHUB_TOKEN", "")
    gh_headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        gh_headers["Authorization"] = f"Bearer {token}"

    head_sha = pr.get("head", {}).get("sha", "")
    try:
        pr_resp = requests.get(
            f"https://api.github.com/repos/{repo.get('full_name', '')}/pulls/{pr.get('number', '')}",
            headers=gh_headers,
            timeout=10,
        )
        pr_resp.raise_for_status()
        head_sha = pr_resp.json().get("head", {}).get("sha", head_sha)
    except Exception as exc:
        logger.warning("dealing_reopo_func: failed to fetch fresh PR data: %s", exc)

    check_runs = get_pr_check_runs(repo.get("full_name", ""), head_sha) if head_sha else []
    if check_runs:
        checks_lines = "".join(
            "<tr>"
            f'<td style="padding:4px 8px;">{"✅" if cr.get("conclusion") == "success" else "❌" if cr.get("conclusion") in ("failure", "cancelled", "timed_out") else "⏳"}</td>'
            f'<td style="padding:4px 8px;"><a href="{cr.get("html_url", "")}">{cr.get("name", "")}</a></td>'
            f'<td style="padding:4px 8px;">{cr.get("status", "")}</td>'
            f'<td style="padding:4px 8px;">{cr.get("conclusion") or "in_progress"}</td>'
            "</tr>"
            for cr in check_runs
        )
        checks_html = (
                "<br><b>🔍 Check Runs:</b>"
                '<table style="border-collapse:collapse;width:100%;">'
                '<tr style="background:#f0f0f0;">'
                '<th style="padding:4px 8px;text-align:left;"></th>'
                '<th style="padding:4px 8px;text-align:left;">Name</th>'
                '<th style="padding:4px 8px;text-align:left;">Status</th>'
                '<th style="padding:4px 8px;text-align:left;">Conclusion</th>'
                "</tr>"
                + checks_lines +
                "</table>"
        )
    else:
        checks_html = "<br><b>🔍 Check Runs:</b> <i>No checks found yet (may still be queued)</i>"
    logger.info("Check runs for PR #%s: %s", pr.get('number'), checks_html)

    # Fetch raw diff content and append to description
    diff_content = get_pr_diff_repo_number(repo.get("full_name", ""), str(pr.get("number", "")))
    if diff_content:
        request_payload["description"] += (
            "<br><br><b>📄 Diff:</b>"
            '<div style="background:#0d1117;border-radius:6px;padding:16px;overflow-x:auto;border:1px solid #30363d;">'
            f'<pre style="margin:0;padding:0;background:transparent;border:none;"><code style="color:#c9d1d9;font-family:SFMono-Regular,Consolas,Liberation Mono,Menlo,monospace;font-size:12px;line-height:1.6;white-space:pre;">{diff_content}</code></pre>'
            '</div>'
        )

    request_payload["description"] += checks_html

    # Add more criteria based on PR title, description, labels, etc. as needed
    result = _submit_approval_request(request_payload)
    logger.info(f"Approval request result: {result}")

    # If all criteria are met, return True to indicate that this PR should be processed further (e.g., trigger CI, assign reviewers)
    return True