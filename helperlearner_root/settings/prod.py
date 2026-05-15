"""Production settings."""
from .base import *
from decouple import config
import dj_database_url
from django.core.exceptions import ImproperlyConfigured

DEBUG = False

SECRET_KEY = config('SECRET_KEY')
if (
    SECRET_KEY in {'unsafe-secret-for-dev', 'dev-secret-for-helperlearner-please-change'}
    or len(SECRET_KEY) < 50
    or len(set(SECRET_KEY)) < 5
    or SECRET_KEY.startswith('django-insecure-')
):
    raise ImproperlyConfigured(
        'Set a long, random SECRET_KEY for production (minimum 50 chars, high entropy).'
    )

ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='',
    cast=lambda v: [s.strip() for s in v.split(',') if s.strip()],
)
if not ALLOWED_HOSTS or '*' in ALLOWED_HOSTS:
    raise ImproperlyConfigured('Set ALLOWED_HOSTS to explicit production hostnames (no wildcard).')

DATABASES = {
    'default': dj_database_url.config(
        default=config('DATABASE_URL'),
        conn_max_age=config('DATABASE_CONN_MAX_AGE', default=600, cast=int),
        ssl_require=env_bool('DATABASE_SSL_REQUIRE', default=True),
    )
}

# Recommended production security
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', default=True)
