import os
from decouple import config
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', config('DJANGO_SETTINGS_MODULE', default='helperlearner_root.settings.dev'))

django_asgi_app = get_asgi_application()

try:  # pragma: no cover - optional runtime dependency
    from channels.auth import AuthMiddlewareStack
    from channels.routing import ProtocolTypeRouter, URLRouter

    from marketplace.routing import websocket_urlpatterns

    application = ProtocolTypeRouter(
        {
            'http': django_asgi_app,
            'websocket': AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
        }
    )
except Exception:
    application = django_asgi_app
