from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from django.views.generic.base import RedirectView

from accounts import views as account_views
from helperlearner_root import views as core_views

from accounts import views as account_views
from helperlearner_root import views as core_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('favicon.ico', RedirectView.as_view(url='/static/favicon.svg', permanent=True), name='favicon'),
    path('healthz/', core_views.health_check, name='health_check'),
    path('', include('marketplace.urls')),
    path('kp/claim-daily/', account_views.claim_daily_kp, name='claim_daily_kp'),
    path('kp/transfer/', account_views.transfer_kp, name='transfer_kp'),
    path('accounts/', include('accounts.urls')),
    path('notifications/', include('notifications.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
