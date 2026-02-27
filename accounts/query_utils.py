from django.db.models import Avg, Case, Count, ExpressionWrapper, F, FloatField, Q, Value, When
from django.db.models.functions import Coalesce, Greatest, Least


def annotate_user_metrics(queryset):
    """Annotate users with rating, delivery, and trust metrics for profile/ranking surfaces."""
    return (
        queryset.annotate(
            avg_rating=Avg('ratings_received__score'),
            ratings_count=Count('ratings_received', distinct=True),
            helped_count=Count('accepted_tasks', filter=Q(accepted_tasks__status='resolved'), distinct=True),
            posted_count=Count('helprequest', distinct=True),
            resolved_posted_count=Count('helprequest', filter=Q(helprequest__status='resolved'), distinct=True),
            canceled_posted_count=Count('helprequest', filter=Q(helprequest__status='canceled'), distinct=True),
        )
        .annotate(
            success_rate=Case(
                When(
                    posted_count__gt=0,
                    then=ExpressionWrapper(
                        Value(100.0) * F('resolved_posted_count') / F('posted_count'),
                        output_field=FloatField(),
                    ),
                ),
                default=Value(0.0),
                output_field=FloatField(),
            )
        )
        .annotate(
            basic_trust_score=Least(
                Value(100.0),
                Greatest(
                    Value(0.0),
                    ExpressionWrapper(
                        (Coalesce(F('avg_rating'), Value(0.0)) * Value(15.0))
                        + (F('helped_count') * Value(2.0))
                        + (F('success_rate') * Value(0.35))
                        - (F('canceled_posted_count') * Value(1.5)),
                        output_field=FloatField(),
                    ),
                ),
            )
        )
    )
