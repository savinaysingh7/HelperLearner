from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Admin listing for user notifications with bulk read action."""

    list_display = ('user', 'message', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('message', 'user__username')
    actions = ('mark_all_read',)

    @admin.action(description='Mark selected notifications as read')
    def mark_all_read(self, request, queryset):
        """Bulk update selected notifications as read."""
        updated = queryset.filter(is_read=False).update(is_read=True)
        self.message_user(request, f'Marked {updated} notification(s) as read.')
