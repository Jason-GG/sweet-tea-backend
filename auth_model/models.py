from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class EmailVerificationCode(models.Model):
    """One-time email verification code used before account registration."""

    email = models.EmailField(db_index=True)
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email", "created_at"], name="auth_model_email_created_idx"),
            models.Index(fields=["email", "verified_at", "consumed_at"], name="auth_model_email_verified_idx"),
        ]

    def __str__(self) -> str:
        return f"EmailVerificationCode(email={self.email}, verified={self.is_verified}, consumed={self.is_consumed})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_verified(self) -> bool:
        return self.verified_at is not None

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    @property
    def can_register(self) -> bool:
        return self.is_verified and not self.is_consumed and not self.is_expired

    def set_code(self, code: str) -> None:
        self.code_hash = make_password(code)

    def matches_code(self, code: str) -> bool:
        return check_password(code, self.code_hash)

    @classmethod
    def consume_active_for_email(cls, email: str) -> None:
        for verification in cls.objects.filter(email=email, consumed_at=None):
            verification.mark_consumed()

    @classmethod
    def create_for_email(cls, email: str, code: str, expires_at) -> "EmailVerificationCode":
        verification = cls(email=email, expires_at=expires_at)
        verification.set_code(code)
        verification.save()
        return verification

    def mark_verified(self) -> None:
        self.verified_at = timezone.now()
        self.save(update_fields=["verified_at", "updated_at"])

    def mark_consumed(self) -> None:
        self.consumed_at = timezone.now()
        self.save(update_fields=["consumed_at", "updated_at"])


class UserProfile(models.Model):
    """Extra profile fields collected during account registration/profile setup."""

    ROLE_USER = "user"
    ROLE_ADMIN = "admin"
    ROLE_CHOICES = [
        (ROLE_USER, "User"),
        (ROLE_ADMIN, "Admin"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_USER)
    display_name = models.CharField(max_length=150, blank=True)
    location = models.CharField(max_length=150, blank=True)
    profile_focus = models.CharField(max_length=100, blank=True)
    receive_updates = models.BooleanField(default=False)
    nickname = models.CharField(max_length=150, blank=True)
    age_group = models.CharField(max_length=50, blank=True)
    language = models.CharField(max_length=50, blank=True, default="Japanese")
    avatar_color = models.CharField(max_length=30, blank=True, default="Lavender")
    self_introduction = models.TextField(blank=True, max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self) -> str:
        return f"UserProfile(user={self.user.username}, display_name={self.display_name})"

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "display_name": self.display_name,
            "location": self.location,
            "profile_focus": self.profile_focus,
            "receive_updates": self.receive_updates,
            "nickname": self.nickname,
            "age_group": self.age_group,
            "language": self.language,
            "avatar_color": self.avatar_color,
            "self_introduction": self.self_introduction,
        }

