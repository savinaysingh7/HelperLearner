from django.contrib import admin
from .models import Skill, HelpRequest, Comment

@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('name',)

@admin.register(HelpRequest)
class HelpRequestAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'skill_needed', 'kp_bounty', 'status', 'created_at')
    list_filter = ('status', 'skill_needed')
    search_fields = ('title', 'description')

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('user', 'request', 'created_at')
    list_filter = ('created_at',)
