from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'requests', views.HelpRequestViewSet, basename='request')
router.register(r'jobs', views.FreelanceJobViewSet, basename='api-job')
router.register(r'users', views.UserViewSet, basename='api-user')
router.register(r'skills', views.SkillViewSet, basename='api-skill')

urlpatterns = [
    path('', views.home, name='home'),
    path('browse/', views.request_list, name='request_list'),
    path('search/', views.unified_search, name='search'),
    path('feed/', views.activity_feed, name='activity_feed'),
    path('saved-searches/', views.saved_searches, name='saved_searches'),
    path('saved-searches/save-current/', views.save_current_search, name='save_current_search'),
    path('saved-searches/<int:pk>/toggle/', views.toggle_saved_search, name='toggle_saved_search'),
    path('saved-searches/<int:pk>/delete/', views.delete_saved_search, name='delete_saved_search'),
    path('jobs/', views.freelance_job_list, name='freelance_job_list'),
    path('jobs/post/', views.post_freelance_job, name='post_freelance_job'),
    path('jobs/<int:pk>/', views.freelance_job_detail, name='freelance_job_detail'),
    path('jobs/<int:pk>/claim/', views.claim_freelance_job, name='claim_freelance_job'),
    path('jobs/<int:pk>/milestones/add/', views.add_job_milestone, name='add_job_milestone'),
    path('jobs/<int:pk>/milestones/<int:milestone_id>/submit/', views.submit_job_milestone, name='submit_job_milestone'),
    path('jobs/<int:pk>/milestones/<int:milestone_id>/release/', views.release_job_milestone, name='release_job_milestone'),
    path('jobs/<int:pk>/dispute/', views.open_job_dispute, name='open_job_dispute'),
    path('jobs/<int:pk>/cancel/', views.cancel_freelance_job, name='cancel_freelance_job'),
    path('wallet/', views.wallet_overview, name='wallet_overview'),
    path('post/assist/', views.ai_request_assist, name='ai_request_assist'),
    path('post/', views.create_request, name='create_request'),
    path('request/<int:pk>/', views.request_detail, name='request_detail'),
    path('request/<int:pk>/edit/', views.edit_request, name='edit_request'),
    path('request/<int:pk>/delete/', views.delete_request, name='delete_request'),
    path('request/<int:pk>/rate/', views.rate_request, name='rate_request'),
    path('request/<int:pk>/claim/', views.claim_request, name='claim_request'),
    path('request/<int:pk>/resolve/', views.resolve_request, name='resolve_request'),
    path('request/<int:pk>/cancel/', views.cancel_request, name='cancel_request'),
    path('skills/', views.skill_browse, name='skill_browse'),
    path('tags/', views.tag_browse, name='tag_browse'),
    path('leaderboard/', views.leaderboard, name='leaderboard'),
    path('api/search/', views.SearchViewSet.as_view({'get': 'list'}), name='api-search'),
    path('api/', include(router.urls)),
]
