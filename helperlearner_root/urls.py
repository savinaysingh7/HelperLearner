from django.contrib import admin
from django.urls import path, include

from accounts import views as account_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('marketplace.urls')),
    path('kp/claim-daily/', account_views.claim_daily_kp, name='claim_daily_kp'),
    path('kp/transfer/', account_views.transfer_kp, name='transfer_kp'),
    path('accounts/', include('accounts.urls')),
    path('notifications/', include('notifications.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
]
