import os
from decouple import config
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', config('DJANGO_SETTINGS_MODULE', default='helperlearner_root.settings.dev'))

application = get_asgi_application()
