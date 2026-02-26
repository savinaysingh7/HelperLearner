from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health_check(request):
    """Return a lightweight health response for load balancers and uptime checks."""
    return JsonResponse({"status": "ok", "service": "helperlearner"})
