import logging

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.contrib.staticfiles import finders
from django.http import Http404, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


def _check_database():
    """Return database probe result as (ok, error_message)."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True, ""
    except Exception as exc:  # pragma: no cover - defensive runtime check
        logger.warning("Readiness DB check failed: %s", exc)
        return False, str(exc)


def _check_cache():
    """Return cache probe result as (ok, error_message)."""
    probe_key = "health:readyz:probe"
    probe_value = "ok"
    try:
        cache.set(probe_key, probe_value, timeout=15)
        if cache.get(probe_key) != probe_value:
            raise RuntimeError("cache probe value mismatch")
        return True, ""
    except Exception as exc:  # pragma: no cover - defensive runtime check
        logger.warning("Readiness cache check failed: %s", exc)
        return False, str(exc)


def _check_celery_broker():
    """Return Celery broker probe result as (ok, error_message)."""
    try:
        from kombu import Connection

        with Connection(
            settings.CELERY_BROKER_URL,
            connect_timeout=settings.READINESS_CHECK_CELERY_TIMEOUT_SECONDS,
        ) as connection_obj:
            connection_obj.connect()
        return True, ""
    except Exception as exc:  # pragma: no cover - defensive runtime check
        logger.warning("Readiness Celery broker check failed: %s", exc)
        return False, str(exc)


@require_GET
def health_check(request):
    """Return a lightweight health response for load balancers and uptime checks."""
    return JsonResponse({"status": "ok", "service": "helperlearner", "version": "v1"})


@require_GET
def readiness_check(request):
    """Return readiness status including database and cache checks."""
    db_ok, db_error = _check_database()
    cache_ok, cache_error = _check_cache()
    errors = []
    celery_required = settings.READINESS_CHECK_CELERY
    celery_ok = None

    if not db_ok:
        errors.append(f"db:{db_error}")
    if not cache_ok:
        errors.append(f"cache:{cache_error}")

    if celery_required:
        celery_ok, celery_error = _check_celery_broker()
        if not celery_ok:
            errors.append(f"celery_broker:{celery_error}")

    required_checks_ok = db_ok and cache_ok and (celery_ok if celery_required else True)
    ready = required_checks_ok
    status_code = 200 if ready else 503
    return JsonResponse(
        {
            "status": "ready" if ready else "degraded",
            "service": "helperlearner",
            "checks": {
                "database": db_ok,
                "cache": cache_ok,
                "celery_broker": celery_ok if celery_required else "skipped",
            },
            "errors": errors,
        },
        status=status_code,
    )


@require_GET
def service_worker(request):
    """Serve the PWA service worker from the root scope."""
    file_path = finders.find('js/service-worker.js')
    if not file_path:
        raise Http404('Service worker not found')
    with open(file_path, 'r', encoding='utf-8') as sw_file:
        response = HttpResponse(sw_file.read(), content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    return response
