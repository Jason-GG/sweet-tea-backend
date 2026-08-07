from functools import wraps

from django.http import JsonResponse

from .models import UserProfile


ROLE_LEVELS = {
    UserProfile.ROLE_USER: 1,
    UserProfile.ROLE_ADMIN: 2,
}


def get_user_role(user) -> str:
    """Return the effective application role for an authenticated Django user."""
    if not user or not user.is_authenticated or not user.is_active:
        return ""
    if user.is_staff or user.is_superuser:
        return UserProfile.ROLE_ADMIN

    profile, _created = UserProfile.objects.get_or_create(user=user)
    return profile.role if profile.role in ROLE_LEVELS else UserProfile.ROLE_USER


def user_has_role(user, minimum_role: str = UserProfile.ROLE_USER) -> bool:
    """Check whether a user has at least the required app role."""
    required_level = ROLE_LEVELS.get(minimum_role)
    if required_level is None:
        return False

    current_role = get_user_role(user)
    return ROLE_LEVELS.get(current_role, 0) >= required_level


def role_required(minimum_role: str = UserProfile.ROLE_USER):
    """Decorator for session-authenticated APIs with role-based access control."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            user = getattr(request, "user", None)
            if not user or not user.is_authenticated:
                return JsonResponse({"error": "Authentication required"}, status=401)
            if not user.is_active:
                return JsonResponse({"error": "Account is inactive"}, status=403)
            if not user_has_role(user, minimum_role):
                return JsonResponse({"error": f"{minimum_role} role required"}, status=403)
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator

