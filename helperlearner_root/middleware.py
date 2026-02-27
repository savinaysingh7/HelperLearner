import logging
import time
import uuid

from django.conf import settings
from django.http import HttpResponseForbidden

from marketplace.experiments import assign_active_experiments

logger = logging.getLogger(__name__)


class SuspensionEnforcementMiddleware:
    """Block state-changing requests when an authenticated user is suspended."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and hasattr(request.user, 'is_currently_suspended')
            and request.user.is_currently_suspended()
            and request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}
            and not request.path.startswith('/admin/')
        ):
            return HttpResponseForbidden('Your account is suspended. Please contact support.')
        return self.get_response(request)


class ExperimentAssignmentMiddleware:
    """Attach active experiment variants to every request context."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        assign_active_experiments(request)
        return self.get_response(request)


class RequestMetricsMiddleware:
    """Attach request-id/timing headers and log very slow requests."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())
        request.request_id = request_id
        start = time.perf_counter()
        slow_threshold_ms = getattr(settings, 'SLOW_REQUEST_THRESHOLD_MS', 900)

        try:
            response = self.get_response(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                'Request failed request_id=%s method=%s path=%s duration_ms=%.2f',
                request_id,
                request.method,
                request.path,
                duration_ms,
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        response['X-Request-ID'] = request_id
        response['X-Response-Time-ms'] = f'{duration_ms:.2f}'

        if duration_ms >= slow_threshold_ms:
            user = request.user.username if getattr(request, 'user', None) and request.user.is_authenticated else 'anonymous'
            logger.warning(
                'Slow request request_id=%s method=%s path=%s status=%s user=%s duration_ms=%.2f',
                request_id,
                request.method,
                request.path,
                getattr(response, 'status_code', 'unknown'),
                user,
                duration_ms,
            )
        return response
