"""
Django settings for the GitHub Project.

All sensitive configuration is loaded from environment variables.
Use a .env file locally (loaded via python-dotenv).
"""

import os
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
    "django.contrib.contenttypes",
    "corsheaders",
    "github",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- No database (this app has no models) ---
DATABASES = {}

# --- CORS ---
CORS_ALLOW_ALL_ORIGINS = os.environ.get("CORS_ALLOW_ALL_ORIGINS", "true").lower() == "true"

# --- Internationalization ---
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

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
