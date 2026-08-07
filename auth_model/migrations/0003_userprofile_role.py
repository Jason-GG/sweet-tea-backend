# Generated for user role-based API authorization.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("auth_model", "0002_userprofile"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="role",
            field=models.CharField(
                choices=[("user", "User"), ("admin", "Admin")],
                default="user",
                max_length=20,
            ),
        ),
    ]

