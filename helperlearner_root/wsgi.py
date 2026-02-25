import os
from decouple import config
from django.core.wsgi import get_wsgi_application

# Allow override via DJANGO_SETTINGS_MODULE, default to dev settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', config('DJANGO_SETTINGS_MODULE', default='helperlearner_root.settings.dev'))

application = get_wsgi_application()
