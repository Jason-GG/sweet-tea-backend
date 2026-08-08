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
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from .auth_data import dealing_reopo_func, get_pr_check_runs, get_pr_diff_repo_number, send_email
from .models import EmailVerificationCode, UserProfile
from .permissions import get_user_role, role_required
logger = logging.getLogger(__name__)

_VERIFICATION_CODE_RE = re.compile(r"^\d{6}$")


def _parse_json_body(request) -> tuple[dict[str, object], JsonResponse | None]:
    try:
        return json.loads(request.body or b"{}"), None
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return {}, JsonResponse({"error": "Invalid JSON body"}, status=400)


def _json_string(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    return "" if value is None else f"{value}"


def _normalize_email(raw_email: str) -> str:
    email = (raw_email or "").strip().lower()
    validate_email(email)
    return email


def _generate_verification_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _json_bool(data: dict[str, object], key: str) -> bool:
    value = data.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _email_verification_enabled() -> bool:
    return bool(getattr(settings, "EMAIL_VERIFICATION_ENABLED", True))


def _limit(value: str, max_length: int) -> str:
    return value.strip()[:max_length]


def _user_to_dict(user: User) -> dict:
    return {
        "id": user.pk,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": get_user_role(user),
    }


def _profile_values_from_request(data: dict[str, object], existing_profile: UserProfile | None = None) -> dict:
    def current(field_name: str, default: str = "") -> str:
        return getattr(existing_profile, field_name, default) if existing_profile else default

    return {
        "display_name": _limit(_json_string(data, "display_name"), 150) if "display_name" in data else current("display_name"),
        "location": _limit(_json_string(data, "location"), 150) if "location" in data else current("location"),
        "profile_focus": _limit(_json_string(data, "profile_focus"), 100) if "profile_focus" in data else current("profile_focus"),
        "receive_updates": _json_bool(data, "receive_updates") if "receive_updates" in data else (existing_profile.receive_updates if existing_profile else False),
        "nickname": _limit(_json_string(data, "nickname"), 150) if "nickname" in data else current("nickname"),
        "age_group": _limit(_json_string(data, "age_group"), 50) if "age_group" in data else current("age_group"),
        "language": (_limit(_json_string(data, "language"), 50) or "Japanese") if "language" in data else current("language", "Japanese"),
        "avatar_color": (_limit(_json_string(data, "avatar_color"), 30) or "Lavender") if "avatar_color" in data else current("avatar_color", "Lavender"),
        "self_introduction": _limit(_json_string(data, "self_introduction"), 300) if "self_introduction" in data else current("self_introduction"),
    }


@method_decorator(csrf_exempt, name="dispatch")
class RequestEmailVerificationCodeView(View):
    """POST /api/auth/request-code/ with {"email": "user@example.com"}."""

    def post(self, request):
        data, error_response = _parse_json_body(request)
        if error_response:
            return error_response

        try:
            email_address = f"{_normalize_email(_json_string(data, 'email'))}"
        except ValidationError:
            return JsonResponse({"error": "A valid email is required"}, status=400)

        if User.objects.filter(email__iexact=email_address).exists():
            return JsonResponse({"error": "An account with this email already exists"}, status=409)

        if not _email_verification_enabled():
            return JsonResponse({"message": "Email verification is disabled; register directly"}, status=200)

        code = str(_generate_verification_code())
        expires_at = timezone.now() + timedelta(
            minutes=getattr(settings, "EMAIL_VERIFICATION_CODE_TTL_MINUTES", 10)
        )

        with transaction.atomic():
            EmailVerificationCode.consume_active_for_email(email_address)

            verification = EmailVerificationCode.create_for_email(email_address, code, expires_at)

        recipient_name = _json_string(data, "name")
        try:
            send_email(f"{email_address}", f"{code}", recipient_name)
        except Exception as exc:
            logger.error("Failed to send verification email to %s: %s", email_address, exc, exc_info=True)
            verification.mark_consumed()
            return JsonResponse({"error": "Failed to send verification email"}, status=502)

        return JsonResponse({"message": "Verification code sent"}, status=201)


@method_decorator(csrf_exempt, name="dispatch")
class VerifyEmailCodeView(View):
    """POST /api/auth/verify-code/ with {"email": "...", "code": "123456"}."""

    def post(self, request):
        data, error_response = _parse_json_body(request)
        if error_response:
            return error_response

        try:
            email_address = f"{_normalize_email(_json_string(data, 'email'))}"
        except ValidationError:
            return JsonResponse({"error": "A valid email is required"}, status=400)

        if not _email_verification_enabled():
            return JsonResponse({"message": "Email verification is disabled; register directly"}, status=200)

        code = str(data.get("code", "")).strip()
        if not _VERIFICATION_CODE_RE.match(code):
            return JsonResponse({"error": "A 6-digit verification code is required"}, status=400)

        verification = EmailVerificationCode.objects.filter(
            email=email_address,
            consumed_at__isnull=True,
        ).order_by("-created_at").first()

        if not verification or verification.is_expired:
            if verification and verification.is_expired:
                verification.mark_consumed()
            return JsonResponse({"error": "Verification code is invalid or expired"}, status=400)

        max_attempts = getattr(settings, "EMAIL_VERIFICATION_MAX_ATTEMPTS", 5)
        if verification.attempts >= max_attempts:
            verification.mark_consumed()
            return JsonResponse({"error": "Too many verification attempts; request a new code"}, status=429)

        if not verification.matches_code(code):
            verification.attempts += 1
            verification.save(update_fields=["attempts", "updated_at"])
            return JsonResponse({"error": "Verification code is invalid or expired"}, status=400)

        if not verification.is_verified:
            verification.mark_verified()

        return JsonResponse({"message": "Email verified; you can now register"}, status=200)


@method_decorator(csrf_exempt, name="dispatch")
class RegisterView(View):
    """POST /api/auth/register/ after successful email verification."""

    def post(self, request):
        data, error_response = _parse_json_body(request)
        if error_response:
            return error_response

        try:
            email_address = f"{_normalize_email(_json_string(data, 'email'))}"
        except ValidationError:
            return JsonResponse({"error": "A valid email is required"}, status=400)

        username = _json_string(data, "username").strip()
        password = _json_string(data, "password")
        confirm_password = _json_string(data, "confirm_password")
        first_name = _json_string(data, "first_name").strip()
        last_name = _json_string(data, "last_name").strip()
        display_name = _limit(_json_string(data, "display_name"), 150)
        location = _limit(_json_string(data, "location"), 150)
        profile_focus = _limit(_json_string(data, "profile_focus"), 100)
        receive_updates = _json_bool(data, "receive_updates")
        nickname = _limit(_json_string(data, "nickname"), 150)
        age_group = _limit(_json_string(data, "age_group"), 50)
        language = _limit(_json_string(data, "language"), 50) or "Japanese"
        avatar_color = _limit(_json_string(data, "avatar_color"), 30) or "Lavender"
        self_introduction = _limit(_json_string(data, "self_introduction"), 300)

        if not username:
            username = display_name or nickname or email_address.split("@", 1)[0]

        if not username:
            return JsonResponse({"error": "Username is required"}, status=400)
        if not password:
            return JsonResponse({"error": "Password is required"}, status=400)
        if confirm_password and password != confirm_password:
            return JsonResponse({"error": "Password and confirm_password do not match"}, status=400)
        if User.objects.filter(username__iexact=username).exists():
            return JsonResponse({"error": "Username is already taken"}, status=409)
        if User.objects.filter(email__iexact=email_address).exists():
            return JsonResponse({"error": "An account with this email already exists"}, status=409)

        try:
            validate_password(password)
        except ValidationError as exc:
            return JsonResponse({"error": "Password validation failed", "details": exc.messages}, status=400)

        verification = None
        with transaction.atomic():
            if _email_verification_enabled():
                verification = (
                    EmailVerificationCode.objects.select_for_update()
                    .filter(email=email_address, verified_at__isnull=False)
                    .order_by("-verified_at")
                    .first()
                )
                if not verification:
                    return JsonResponse({"error": "Email must be verified before registration"}, status=403)

            user = User.objects.create_user(
                username=username,
                email=email_address,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )
            profile = UserProfile.objects.create(
                user=user,
                display_name=display_name,
                location=location,
                profile_focus=profile_focus,
                receive_updates=receive_updates,
                nickname=nickname,
                age_group=age_group,
                language=language,
                avatar_color=avatar_color,
                self_introduction=self_introduction,
            )
            if verification and not verification.is_consumed:
                verification.mark_consumed()

        return JsonResponse(
            {
                "message": "Account created",
                "user": {
                    "id": user.pk,
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                },
                "profile": profile.to_dict(),
            },
            status=201,
        )


@method_decorator(csrf_exempt, name="dispatch")
class LoginView(View):
    """POST /api/auth/login/ with {"email": "user@example.com", "password": "..."}."""

    def post(self, request):
        data, error_response = _parse_json_body(request)
        if error_response:
            return error_response

        try:
            email_address = f"{_normalize_email(_json_string(data, 'email'))}"
        except ValidationError:
            return JsonResponse({"error": "A valid email is required"}, status=400)

        password = _json_string(data, "password")
        if not password:
            return JsonResponse({"error": "Password is required"}, status=400)

        user = User.objects.filter(email__iexact=email_address).first()
        if not user or not user.check_password(password):
            return JsonResponse({"error": "Invalid email or password"}, status=403)
        if not user.is_active:
            return JsonResponse({"error": "Account is inactive"}, status=403)

        auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        profile, _created = UserProfile.objects.get_or_create(user=user)

        return JsonResponse(
            {
                "message": "Login successful",
                "user": _user_to_dict(user),
                "profile": profile.to_dict(),
            },
            status=200,
        )


@method_decorator(csrf_exempt, name="dispatch")
class LogoutView(View):
    """POST /api/auth/logout/ clears the current session if one exists."""

    def post(self, request):
        was_authenticated = bool(getattr(request, "user", None) and request.user.is_authenticated)
        auth_logout(request)
        return JsonResponse(
            {
                "message": "Logout successful",
                "was_authenticated": was_authenticated,
            },
            status=200,
        )


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(role_required(UserProfile.ROLE_USER), name="dispatch")
class AccountUpdateView(View):
    """POST /api/auth/account/update/ to modify account/profile data after password verification."""

    def post(self, request):
        data, error_response = _parse_json_body(request)
        if error_response:
            return error_response

        try:
            email_address = f"{_normalize_email(_json_string(data, 'email'))}"
        except ValidationError:
            return JsonResponse({"error": "A valid email is required"}, status=400)

        current_password = _json_string(data, "current_password")
        if not current_password:
            return JsonResponse({"error": "current_password is required"}, status=400)

        user = User.objects.filter(email__iexact=email_address).first()
        if not user or not user.check_password(current_password):
            return JsonResponse({"error": "Invalid email or current_password"}, status=403)
        if user.pk != request.user.pk:
            return JsonResponse({"error": "You can only update your own account"}, status=403)

        requested_email = _json_string(data, "new_email").strip()
        if requested_email:
            try:
                requested_email = f"{_normalize_email(requested_email)}"
            except ValidationError:
                return JsonResponse({"error": "new_email must be a valid email"}, status=400)
            if requested_email != user.email.lower():
                return JsonResponse({"error": "Email changes require a separate email verification flow"}, status=400)

        new_username = _json_string(data, "username").strip()
        first_name = _json_string(data, "first_name").strip() if "first_name" in data else user.first_name
        last_name = _json_string(data, "last_name").strip() if "last_name" in data else user.last_name
        new_password = _json_string(data, "new_password")
        confirm_new_password = _json_string(data, "confirm_new_password")

        if new_username and new_username.lower() != user.username.lower():
            if User.objects.filter(username__iexact=new_username).exclude(pk=user.pk).exists():
                return JsonResponse({"error": "Username is already taken"}, status=409)
        else:
            new_username = user.username

        if new_password:
            if new_password != confirm_new_password:
                return JsonResponse({"error": "new_password and confirm_new_password do not match"}, status=400)
            try:
                validate_password(new_password, user)
            except ValidationError as exc:
                return JsonResponse({"error": "Password validation failed", "details": exc.messages}, status=400)

        with transaction.atomic():
            user.username = new_username
            user.first_name = first_name
            user.last_name = last_name
            if new_password:
                user.set_password(new_password)
            user.save()

            profile, _created = UserProfile.objects.get_or_create(user=user)
            profile_values = _profile_values_from_request(data, profile)
            for field_name, value in profile_values.items():
                setattr(profile, field_name, value)
            profile.save()

        return JsonResponse(
            {
                "message": "Account updated",
                "user": _user_to_dict(user),
                "profile": profile.to_dict(),
            },
            status=200,
        )


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(role_required(UserProfile.ROLE_USER), name="dispatch")
class CurrentUserRoleView(View):
    """GET /api/auth/role/ returns the signed-in user's effective role."""

    def get(self, request):
        profile, _created = UserProfile.objects.get_or_create(user=request.user)
        return JsonResponse(
            {
                "user": _user_to_dict(request.user),
                "role": get_user_role(request.user),
                "profile": profile.to_dict(),
            },
            status=200,
        )


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(role_required(UserProfile.ROLE_ADMIN), name="dispatch")
class UserRoleView(View):
    """GET/PUT/PATCH /api/users/<user_id>/role/ for admin-only role management."""

    def _get_target_user(self, user_id: int) -> User | None:
        return User.objects.filter(pk=user_id).first()

    def get(self, request, user_id: int):
        target_user = self._get_target_user(user_id)
        if not target_user:
            return JsonResponse({"error": "User not found"}, status=404)

        profile, _created = UserProfile.objects.get_or_create(user=target_user)
        return JsonResponse(
            {
                "user": _user_to_dict(target_user),
                "role": get_user_role(target_user),
                "profile": profile.to_dict(),
            },
            status=200,
        )

    def put(self, request, user_id: int):
        data, error_response = _parse_json_body(request)
        if error_response:
            return error_response

        requested_role = _json_string(data, "role").strip().lower()
        valid_roles = {choice[0] for choice in UserProfile.ROLE_CHOICES}
        if requested_role not in valid_roles:
            return JsonResponse(
                {
                    "error": "role must be one of: user, admin",
                    "valid_roles": sorted(valid_roles),
                },
                status=400,
            )
        if request.user.pk == user_id and requested_role != UserProfile.ROLE_ADMIN:
            return JsonResponse({"error": "Admins cannot remove their own admin role"}, status=400)

        with transaction.atomic():
            target_user = User.objects.select_for_update().filter(pk=user_id).first()
            if not target_user:
                return JsonResponse({"error": "User not found"}, status=404)

            profile, _created = UserProfile.objects.select_for_update().get_or_create(user=target_user)
            profile.role = requested_role
            profile.save(update_fields=["role", "updated_at"])

        return JsonResponse(
            {
                "message": "User role updated",
                "user": _user_to_dict(target_user),
                "role": get_user_role(target_user),
                "profile": profile.to_dict(),
            },
            status=200,
        )

    def patch(self, request, user_id: int):
        return self.put(request, user_id)


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
@method_decorator(role_required(UserProfile.ROLE_USER), name="dispatch")
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



@role_required(UserProfile.ROLE_USER)
def health_check(request):
    """Simple health check endpoint."""
    return JsonResponse({"status": "ok"})