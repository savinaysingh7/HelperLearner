"""Development settings."""
from .base import *
from decouple import config
import dj_database_url

DEBUG = config('DEBUG', default=True, cast=bool)

# For development, allow all hosts by default
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=lambda v: [s.strip() for s in v.split(',')])

# Keep local/dev traffic on HTTP even if the parent shell has production-like
# values such as DEBUG=release.
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_PROXY_SSL_HEADER = None

# Use console email backend for dev
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Default to local SQLite for dev unless DATABASE_URL is explicitly provided.
DATABASES = {
    'default': dj_database_url.config(
        default=config('DATABASE_URL', default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
    )
}
