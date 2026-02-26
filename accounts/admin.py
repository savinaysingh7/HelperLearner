from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db.models import Avg

from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """Admin configuration for custom users with KP and rating visibility."""

    model = CustomUser
    list_display = [
        'username',
        'email',
        'knowledge_points',
        'wallet_inr',
        'compliance_verified',
        'notification_preference',
        'avg_rating_display',
        'is_staff',
    ]
    readonly_fields = ('avg_rating_display',)
    fieldsets = UserAdmin.fieldsets + (
        (
            'Marketplace Profile',
            {
                'fields': (
                    'bio',
                    'knowledge_points',
                    'wallet_inr',
                    'compliance_verified',
                    'skills',
                    'last_kp_claim',
                    'notification_preference',
                    'avg_rating_display',
                )
            },
        ),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            'Marketplace Profile',
            {'fields': ('bio', 'knowledge_points', 'wallet_inr', 'compliance_verified', 'skills', 'last_kp_claim', 'notification_preference')},
        ),
    )
    filter_horizontal = ('skills',)

    def get_queryset(self, request):
        """Annotate users with average rating for admin display."""
        queryset = super().get_queryset(request)
        return queryset.annotate(_avg_rating=Avg('ratings_received__score'))

    @admin.display(description='Avg Rating')
    def avg_rating_display(self, obj):
        """Show a rounded average rating for the user when available."""
        avg_rating = getattr(obj, '_avg_rating', None)
        if avg_rating is None:
            return '-'
        return round(avg_rating, 2)
