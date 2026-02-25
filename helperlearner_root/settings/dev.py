"""Development settings."""
from .base import *
from decouple import config
import dj_database_url

DEBUG = config('DEBUG', default=True, cast=bool)

# For development, allow all hosts by default
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=lambda v: [s.strip() for s in v.split(',')])

# Use console email backend for dev
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Default to local SQLite for dev unless DATABASE_URL is explicitly provided.
DATABASES = {
    'default': dj_database_url.config(
        default=config('DATABASE_URL', default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
    )
}
