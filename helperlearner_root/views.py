from django.contrib.staticfiles import finders
from django.http import Http404, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health_check(request):
    """Return a lightweight health response for load balancers and uptime checks."""
    return JsonResponse({"status": "ok", "service": "helperlearner"})


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
