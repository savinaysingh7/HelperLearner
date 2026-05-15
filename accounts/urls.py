from django.urls import path
from . import views
from .export import export_my_data

urlpatterns = [
    path('signup/', views.signup, name='signup'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile, name='profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('u/<str:username>/', views.public_profile, name='public_profile'),
    path('export/', export_my_data, name='export_my_data'),
]
