"""
TutorBridge Django settings.

All secrets and environment-specific values come from environment variables
(set in cPanel "Setup Python App" in production, or a local .env file in
development). Never commit real keys.
"""
import os
import sys
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    return str(env(name, str(default))).lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    return [v.strip() for v in env(name, default).split(",") if v.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)
TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"
SECRET_KEY = env("DJANGO_SECRET_KEY") or ("dev-insecure-key-change-me" if DEBUG or TESTING else None)
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY must be set when DEBUG is off")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "http://localhost:5173")
SITE_URL = env("SITE_URL", "http://localhost:5173")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "core",
    "accounts",
    "parents",
    "tutors",
    "vetting",
    "matching",
    "bookings",
    "payments",
    "messaging",
    "trust",
    "backoffice",
    "website",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounts.middleware.StaffIdleTimeoutMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Database -------------------------------------------------------------
# Production: MySQL 8 / MariaDB 10.6+ (InnoDB, utf8mb4, strict mode).
# Local development falls back to SQLite when DB_ENGINE is not "mysql".
if env("DB_ENGINE", "sqlite") == "mysql":
    import pymysql

    pymysql.install_as_MySQLdb()
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": env("DB_NAME", "tutorbridge"),
            "USER": env("DB_USER", "tutorbridge"),
            "PASSWORD": env("DB_PASSWORD", ""),
            "HOST": env("DB_HOST", "localhost"),
            "PORT": env("DB_PORT", "3306"),
            "CONN_MAX_AGE": 60,
            "OPTIONS": {
                "charset": "utf8mb4",
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES', time_zone='+00:00'",
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

# --- Auth & passwords -----------------------------------------------------
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
AUTHENTICATION_BACKENDS = ["accounts.backends.EmailOrPhoneBackend"]
PASSWORD_RESET_TIMEOUT = 30 * 60  # AUTH-04: 30 minutes, single use
LOGIN_LOCKOUT_ATTEMPTS = 5  # AUTH-05
LOGIN_LOCKOUT_MINUTES = 15
STAFF_IDLE_TIMEOUT = timedelta(hours=8)

# --- Sessions & cookies ---------------------------------------------------
SESSION_COOKIE_AGE = 14 * 24 * 3600  # 2 weeks max for users
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", not DEBUG)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 0 if DEBUG else int(env("DJANGO_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

# --- REST framework -------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_THROTTLE_RATES": {
        "login": "10/min",
        "otp": "5/min",
        "password_reset": "5/hour",
        "payment": "20/min",
        "messages": "30/min",
        "anon": "120/min",
    },
}

# --- I18N -----------------------------------------------------------------
LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True

# --- Static & private media -----------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = Path(env("STATIC_ROOT", BASE_DIR / "staticfiles"))
# Compiled React client (client/dist) is served as the SPA shell.
CLIENT_DIST_DIR = Path(env("CLIENT_DIST_DIR", BASE_DIR.parent / "client" / "dist"))
STATICFILES_DIRS = [CLIENT_DIST_DIR] if CLIENT_DIST_DIR.exists() else []
# TUT-06: uploads stored OUTSIDE the public web root, served only via permission-checked views.
PRIVATE_MEDIA_ROOT = Path(env("PRIVATE_MEDIA_ROOT", BASE_DIR / "private_media"))
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024

# --- Cache (database-backed, works on any cPanel host) --------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "cache_table",
    }
}

# --- Field encryption -----------------------------------------------------
# Comma-separated Fernet keys; the first is used to encrypt, all are tried to decrypt (key rotation).
FIELD_ENCRYPTION_KEYS = env_list("FIELD_ENCRYPTION_KEYS", "")

# --- Integrations ---------------------------------------------------------
# Public demo deployments: allows seed_demo and the simulated "fake" gateway without turning DEBUG on.
DEMO_MODE = env_bool("DEMO_MODE", False)
PAYMENT_GATEWAY = env("PAYMENT_GATEWAY", "paystack")  # paystack | flutterwave | fake (dev/demo only)
PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY", "")
PAYSTACK_PUBLIC_KEY = env("PAYSTACK_PUBLIC_KEY", "")
FLUTTERWAVE_SECRET_KEY = env("FLUTTERWAVE_SECRET_KEY", "")
FLUTTERWAVE_WEBHOOK_HASH = env("FLUTTERWAVE_WEBHOOK_HASH", "")
SMS_PROVIDER = env("SMS_PROVIDER", "console")  # termii | console
TERMII_API_KEY = env("TERMII_API_KEY", "")
TERMII_SENDER_ID = env("TERMII_SENDER_ID", "TutorBridge")
KYC_PROVIDER = env("KYC_PROVIDER", "manual")  # manual | dojah | prembly ...
GOOGLE_MAPS_API_KEY = env("GOOGLE_MAPS_API_KEY", "")  # optional; OpenStreetMap is used when empty
GEO_PROVIDER = env("GEO_PROVIDER", "off" if TESTING else "nominatim")  # nominatim | off (google is chosen automatically by key)
GEO_CONTACT_EMAIL = env("GEO_CONTACT_EMAIL", "hello@tutorbridge.ng")  # required by OpenStreetMap's usage policy
SAFETY_OFFICER_PHONE = env("SAFETY_OFFICER_PHONE", "")
SAFETY_OFFICER_EMAIL = env("SAFETY_OFFICER_EMAIL", "safety@tutorbridge.ng")

EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "TutorBridge <no-reply@tutorbridge.ng>")

# --- Error tracking (optional) ---------------------------------------------
SENTRY_DSN = env("SENTRY_DSN", "")
if SENTRY_DSN and not TESTING:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        environment=env("SENTRY_ENVIRONMENT", "production"),
        traces_sample_rate=float(env("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
        send_default_pii=False,  # no emails, IPs, cookies or request bodies (children's and payment data)
    )

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
