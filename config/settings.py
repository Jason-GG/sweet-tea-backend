"""
Django settings for the GitHub Project.

All sensitive configuration is loaded from environment variables.
Use a .env file locally (loaded via python-dotenv).
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Core Django ---
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "change-me-in-production")
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "*").split(",") if h.strip()]

# --- Application definition ---
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "corsheaders",
    "auth_model.apps.AuthModelConfig",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Database ---
# The deployment currently names the PostgreSQL settings MYSQL_*; keep those as
# fallbacks while preferring clearer POSTGRES_* environment variable names.
DB_HOST = os.environ.get("POSTGRES_HOST") or os.environ.get("MYSQL_HOST", "")
if "test" in sys.argv and not DB_HOST:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB") or os.environ.get("MYSQL_DB", "sweettea"),
            "HOST": DB_HOST,
            "USER": os.environ.get("POSTGRES_USER") or os.environ.get("MYSQL_USER", ""),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD") or os.environ.get("MYSQL_PASSWORD", ""),
            "PORT": os.environ.get("POSTGRES_PORT") or os.environ.get("MYSQL_PORT", "5432"),
            "CONN_MAX_AGE": int(os.environ.get("POSTGRES_CONN_MAX_AGE", "60")),
        }
    }

# --- CORS ---
CORS_ALLOW_ALL_ORIGINS = os.environ.get("CORS_ALLOW_ALL_ORIGINS", "true").lower() == "true"

# --- Internationalization ---
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Logging ---
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(asctime)s %(name)s %(levelname)s %(module)s %(funcName)s - %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("LOG_LEVEL", "INFO"),
    },
}

# ---------------------------------------------------------------------------
# GitHub webhook configuration
# ---------------------------------------------------------------------------
GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# ---------------------------------------------------------------------------
# External API configuration (for approval requests workflow engine)
# ---------------------------------------------------------------------------
APPROVAL_REQUEST_URL = os.environ.get("APPROVAL_REQUEST_URL", "http://cmdb-backend-service:81/api/ApprovalRequests")
APPROVAL_REQUEST_AUTH = os.environ.get("APPROVAL_REQUEST_AUTH", "")

# ---------------------------------------------------------------------------
# MailerSend / email verification configuration
# ---------------------------------------------------------------------------
MAILERSEND_API_TOKEN = os.environ.get("MAILERSEND_API_TOKEN", "")
MAILERSEND_API_URL = os.environ.get("MAILERSEND_API_URL", "https://api.mailersend.com/v1/email")
MAILERSEND_FROM_EMAIL = os.environ.get("MAILERSEND_FROM_EMAIL", "")
MAILERSEND_FROM_NAME = os.environ.get("MAILERSEND_FROM_NAME", "Sweet Tea")
EMAIL_VERIFICATION_CODE_TTL_MINUTES = int(os.environ.get("EMAIL_VERIFICATION_CODE_TTL_MINUTES", "10"))
EMAIL_VERIFICATION_MAX_ATTEMPTS = int(os.environ.get("EMAIL_VERIFICATION_MAX_ATTEMPTS", "5"))

