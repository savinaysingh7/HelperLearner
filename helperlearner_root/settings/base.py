"""Base settings shared by all environments."""
import logging
from pathlib import Path
import sys

import dj_database_url
from decouple import config
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TESTING = 'test' in sys.argv
logger = logging.getLogger(__name__)
LOG_FILE_PATH = Path(config("LOG_FILE", default=str(BASE_DIR / "logs" / "server.log")))
LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)


def env_bool(name, default=False):
    """Parse boolean env values safely without crashing on invalid input."""
    raw_value = config(name, default=default)
    if isinstance(raw_value, bool):
        return raw_value

    normalized = str(raw_value).strip().lower()
    truthy = {'1', 'true', 'yes', 'on'}
    falsy = {'0', 'false', 'no', 'off', ''}
    false_aliases = {'release', 'prod', 'production'}

    if normalized in truthy:
        return True
    if normalized in falsy or normalized in false_aliases:
        return False

    logger.warning("Invalid boolean value for %s=%r. Falling back to default=%s.", name, raw_value, default)
    return default


SECRET_KEY = config("SECRET_KEY", default="unsafe-secret-for-dev")
DEBUG = env_bool("DEBUG", default=False)

if not DEBUG and SECRET_KEY == "unsafe-secret-for-dev":
    raise ImproperlyConfigured(
        "SECRET_KEY must be set to a unique, unpredictable value in production. "
        "Set the SECRET_KEY environment variable."
    )

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1" if DEBUG else "",
    cast=lambda value: [host.strip() for host in value.split(",") if host.strip()],
)

# Render.com sets RENDER_EXTERNAL_HOSTNAME automatically
RENDER_EXTERNAL_HOSTNAME = config("RENDER_EXTERNAL_HOSTNAME", default="")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "django_filters",
    "axes",
    "accounts",
    "marketplace",
    "notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "helperlearner_root.middleware.RequestMetricsMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "helperlearner_root.middleware.ExperimentAssignmentMiddleware",
    "helperlearner_root.middleware.SuspensionEnforcementMiddleware",
    "axes.middleware.AxesMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "helperlearner_root.urls"

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
                "notifications.context_processors.unread_notifications_count",
                "marketplace.context_processors.active_experiments",
                "marketplace.context_processors.unread_chat_threads_count",
            ],
        },
    },
]

WSGI_APPLICATION = "helperlearner_root.wsgi.application"

try:  # pragma: no cover - optional dependency
    import channels  # noqa: F401

    HAS_CHANNELS = True
    INSTALLED_APPS.append("channels")
    ASGI_APPLICATION = "helperlearner_root.asgi.application"
except Exception:
    HAS_CHANNELS = False
    ASGI_APPLICATION = "helperlearner_root.asgi.application"

if HAS_CHANNELS:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }

DATABASES = {
    "default": dj_database_url.config(
        default=config(
            "DATABASE_URL",
            default="postgresql://postgres:postgres@localhost:5432/helperlearner",
        ),
        conn_max_age=config("DATABASE_CONN_MAX_AGE", default=600, cast=int),
        ssl_require=env_bool("DATABASE_SSL_REQUIRE", default=False),
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
        "marketplace.api_auth.ApiKeyAuthentication",
    ],
}

REDIS_URL = config("REDIS_URL", default="").strip()
CACHE_LOCATION = config("CACHE_LOCATION", default="helperlearner-cache")
CACHE_BACKEND = config("CACHE_BACKEND", default="").strip()

if not CACHE_BACKEND and REDIS_URL:
    try:  # pragma: no cover - optional dependency
        import django_redis  # noqa: F401

        CACHE_BACKEND = "django_redis.cache.RedisCache"
    except Exception:
        CACHE_BACKEND = "django.core.cache.backends.locmem.LocMemCache"
        logger.warning("REDIS_URL is set but django-redis is unavailable; falling back to LocMem cache.")

if not CACHE_BACKEND:
    CACHE_BACKEND = "django.core.cache.backends.locmem.LocMemCache"

if CACHE_BACKEND == "django_redis.cache.RedisCache" and not REDIS_URL:
    logger.warning("CACHE_BACKEND is django_redis.cache.RedisCache but REDIS_URL is empty; using LocMem cache.")
    CACHE_BACKEND = "django.core.cache.backends.locmem.LocMemCache"

if CACHE_BACKEND == "django_redis.cache.RedisCache":
    CACHES = {
        "default": {
            "BACKEND": CACHE_BACKEND,
            "LOCATION": REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
            },
            "KEY_PREFIX": "helperlearner",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": CACHE_BACKEND,
            "LOCATION": CACHE_LOCATION,
        }
    }

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

AUTH_USER_MODEL = "accounts.CustomUser"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "home"
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="no-reply@helperlearner.local")
GEMINI_API_KEY = config("GEMINI_API_KEY", default="")
GEMINI_MODEL = config("GEMINI_MODEL", default="gemini-flash-latest")

X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", default=True)
    SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=31536000, cast=int)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

AXES_ENABLED = env_bool("AXES_ENABLED", default=True)
AXES_FAILURE_LIMIT = config("AXES_FAILURE_LIMIT", default=5, cast=int)
AXES_COOLOFF_TIME = config("AXES_COOLOFF_TIME", default=1, cast=int)
AXES_LOCK_OUT_AT_FAILURE = True
AXES_RESET_ON_SUCCESS = True
AXES_VERBOSE = env_bool("AXES_VERBOSE", default=False)

if "test" in sys.argv:
    AXES_ENABLED = False
    AI_SUMMARY_ENABLED = False
    PUBLIC_STATS_CACHE_SECONDS = 0
    CELERY_TASK_ALWAYS_EAGER = True
    WEBHOOK_ASYNC_ENABLED = False
    NOTIFICATION_EMAIL_ASYNC_ENABLED = False
    AUTHENTICATION_BACKENDS = [
        "django.contrib.auth.backends.ModelBackend",
    ]
    SILENCED_SYSTEM_CHECKS = ["axes.W003"]
    STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
    MIDDLEWARE = [mw for mw in MIDDLEWARE if mw != "whitenoise.middleware.WhiteNoiseMiddleware"]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_context": {
            "()": "helperlearner_root.logging_context.RequestContextFilter",
        },
    },
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} [req_id={request_id} user={request_user} method={request_method} path={request_path}] {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} [req_id={request_id}] {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "filters": ["request_context"],
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_FILE_PATH,
            "encoding": "utf-8",
            "errors": "replace",
            "maxBytes": 1024 * 1024,
            "backupCount": 3,
            "formatter": "verbose",
            "filters": ["request_context"],
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console", "file"],
            "level": "ERROR",
            "propagate": False,
        },
        "django.security.csrf": {
            "handlers": ["console", "file"],
            "level": "ERROR",
            "propagate": False,
        },
        "marketplace": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "accounts": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "notifications": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "helperlearner_root": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "WARNING",
    },
}

if "test" in sys.argv:
    # Keep test runs deterministic and avoid mutating tracked log files.
    LOGGING["handlers"].pop("file", None)
    for logger_name in ["django", "marketplace", "accounts", "notifications", "root"]:
        if logger_name == "root":
            handlers = LOGGING.get("root", {}).get("handlers", [])
        else:
            handlers = LOGGING["loggers"][logger_name].get("handlers", [])
        if "file" in handlers:
            handlers.remove("file")
