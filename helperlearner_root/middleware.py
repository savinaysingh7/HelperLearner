from django.http import HttpResponseForbidden

from marketplace.experiments import assign_active_experiments


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
