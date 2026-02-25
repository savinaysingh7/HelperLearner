from django.contrib import admin

from .models import Comment, HelpRequest, Rating, Skill, Tag


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('name',)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name', 'slug')


@admin.register(HelpRequest)
class HelpRequestAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'skill_needed', 'kp_bounty', 'status', 'expires_at', 'created_at')
    list_filter = ('status', 'skill_needed', 'tags')
    search_fields = ('title', 'description')
    filter_horizontal = ('tags',)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('user', 'request', 'is_private', 'created_at')
    list_filter = ('is_private', 'created_at')


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ('request', 'given_by', 'given_to', 'score', 'created_at')
    list_filter = ('score', 'created_at')
