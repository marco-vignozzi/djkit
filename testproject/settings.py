"""
Django settings used only to run the djkit test suite.

The suite needs PostgreSQL (some tests use its SQL behaviour), so the
connection comes from environment variables. Defaults match the throwaway
container of the README:

    docker run -d -e POSTGRES_PASSWORD=djkit -e POSTGRES_DB=djkit_test \
        -p 55432:5432 postgres:18
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = "djkit-tests-only"
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]
ROOT_URLCONF = "djkit.tests.urls"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DJKIT_TEST_DB_NAME", "djkit_test"),
        "USER": os.environ.get("DJKIT_TEST_DB_USER", "postgres"),
        "PASSWORD": os.environ.get("DJKIT_TEST_DB_PASSWORD", "djkit"),
        "HOST": os.environ.get("DJKIT_TEST_DB_HOST", "localhost"),
        "PORT": os.environ.get("DJKIT_TEST_DB_PORT", "55432"),
    }
}

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "djkit",
]
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# The djkit settings a real project sets (RentalManager/config/settings.py).
TEST_RUNNER = "djkit.testing.runner.VerboseTestRunner"
DJKIT_RELAXED_VALIDATION = False
DJKIT_FORBID_UNKNOWN_QUERY_PARAMS = True
DJKIT_PAGE_SIZES = (10, 25, 50, 100)
DJKIT_PAGE_SIZE = 25
DJKIT_COOLDOWN_SECONDS = 60
DJKIT_AUDIT_EXCLUDED_FIELDS = frozenset({"password", "token_digest", "key_digest"})
DJKIT_AUDIT_MASKED_FIELDS = frozenset({"email"})
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "djkit.auth.UserAttributeSimilarityValidator"},
    {"NAME": "djkit.auth.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
