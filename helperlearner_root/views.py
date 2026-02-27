import logging

from django.core.cache import cache
from django.db import connection
from django.contrib.staticfiles import finders
from django.http import Http404, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@require_GET
def health_check(request):
    """Return a lightweight health response for load balancers and uptime checks."""
    return JsonResponse({"status": "ok", "service": "helperlearner"})


@require_GET
def readiness_check(request):
    """Return readiness status including database and cache checks."""
    db_ok = True
    cache_ok = True
    errors = []

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:  # pragma: no cover - defensive runtime check
        db_ok = False
        errors.append(f"db:{exc}")
        logger.warning("Readiness DB check failed: %s", exc)

    probe_key = "health:readyz:probe"
    probe_value = "ok"
    try:
        cache.set(probe_key, probe_value, timeout=15)
        if cache.get(probe_key) != probe_value:
            raise RuntimeError("cache probe value mismatch")
    except Exception as exc:  # pragma: no cover - defensive runtime check
        cache_ok = False
        errors.append(f"cache:{exc}")
        logger.warning("Readiness cache check failed: %s", exc)

    ready = db_ok and cache_ok
    status_code = 200 if ready else 503
    return JsonResponse(
        {
            "status": "ready" if ready else "degraded",
            "service": "helperlearner",
            "checks": {"database": db_ok, "cache": cache_ok},
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
