# Generated for profile fields collected during account registration.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("auth_model", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("display_name", models.CharField(blank=True, max_length=150)),
                ("location", models.CharField(blank=True, max_length=150)),
                ("profile_focus", models.CharField(blank=True, max_length=100)),
                ("receive_updates", models.BooleanField(default=False)),
                ("nickname", models.CharField(blank=True, max_length=150)),
                ("age_group", models.CharField(blank=True, max_length=50)),
                ("language", models.CharField(blank=True, default="Japanese", max_length=50)),
                ("avatar_color", models.CharField(blank=True, default="Lavender", max_length=30)),
                ("self_introduction", models.TextField(blank=True, max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["user__username"],
            },
        ),
    ]

