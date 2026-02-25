from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create a router and register our viewsets with it.
router = DefaultRouter()
router.register(r'requests', views.HelpRequestViewSet, basename='request')

# The API URLs are now determined automatically by the router.
urlpatterns = [
    path('', views.home, name='home'),
    path('browse/', views.request_list, name='request_list'),
    path('post/', views.create_request, name='create_request'),
    path('request/<int:pk>/', views.request_detail, name='request_detail'),
    path('request/<int:pk>/claim/', views.claim_request, name='claim_request'),
    path('request/<int:pk>/resolve/', views.resolve_request, name='resolve_request'),
    path('request/<int:pk>/cancel/', views.cancel_request, name='cancel_request'),

    # API Endpoints
    path('api/', include(router.urls)),
]
