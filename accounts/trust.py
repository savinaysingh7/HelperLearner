from datetime import timedelta

from django.db.models import Avg, DurationField, ExpressionWrapper, F
from django.utils import timezone

from marketplace.models import FreelanceJob, FreelanceJobProposal, HelpRequest, HelpRequestProposal, JobDispute


def compute_trust_score_v2(user):
    """Compute trust score v2 from on-time, dispute, responsiveness, and streak metrics."""
    completed_jobs = list(
        FreelanceJob.objects.filter(freelancer=user, status='completed').only('id', 'deadline', 'updated_at')
    )
    completed_count = len(completed_jobs)

    on_time_candidates = [job for job in completed_jobs if job.deadline]
    if on_time_candidates:
        on_time_count = sum(1 for job in on_time_candidates if job.updated_at.date() <= job.deadline)
        on_time_rate = round((on_time_count / len(on_time_candidates)) * 100, 2)
    else:
        on_time_rate = 100.0 if completed_count else 0.0

    dispute_count = JobDispute.objects.filter(job__freelancer=user).count()
    dispute_rate = round((dispute_count / completed_count) * 100, 2) if completed_count else 0.0

    request_response = HelpRequestProposal.objects.filter(applicant=user).annotate(
        response_delta=ExpressionWrapper(
            F('created_at') - F('request__created_at'),
            output_field=DurationField(),
        )
    ).aggregate(avg_delta=Avg('response_delta'))['avg_delta']

    job_response = FreelanceJobProposal.objects.filter(applicant=user).annotate(
        response_delta=ExpressionWrapper(
            F('created_at') - F('job__created_at'),
            output_field=DurationField(),
        )
    ).aggregate(avg_delta=Avg('response_delta'))['avg_delta']

    deltas = [value for value in [request_response, job_response] if value is not None]
    if deltas:
        avg_seconds = sum(delta.total_seconds() for delta in deltas) / len(deltas)
        avg_response_minutes = round(avg_seconds / 60, 2)
    else:
        avg_response_minutes = 0.0

    resolved_help = list(
        HelpRequest.objects.filter(accepted_by=user, status='resolved').only('id', 'updated_at').values('id', 'updated_at')
    )
    job_outcomes = []
    disputed_job_ids = set(
        JobDispute.objects.filter(job__freelancer=user).values_list('job_id', flat=True)
    )
    for job in completed_jobs:
        job_outcomes.append(
            {
                'timestamp': job.updated_at,
                'success': job.id not in disputed_job_ids,
            }
        )
    for row in resolved_help:
        job_outcomes.append({'timestamp': row['updated_at'], 'success': True})

    job_outcomes.sort(key=lambda row: row['timestamp'], reverse=True)
    streak = 0
    for row in job_outcomes:
        if row['success']:
            streak += 1
        else:
            break

    # Blend metrics into an interpretable 0-100 score.
    responsiveness_score = 100.0 if avg_response_minutes == 0 else max(0.0, 100.0 - (avg_response_minutes / 30.0))
    raw_score = (
        (on_time_rate * 0.35)
        + ((100.0 - dispute_rate) * 0.35)
        + (responsiveness_score * 0.20)
        + (min(streak, 20) * 0.5)
    )
    trust_score = round(max(0.0, min(100.0, raw_score)), 2)

    return {
        'trust_score_v2': trust_score,
        'on_time_rate': on_time_rate,
        'dispute_rate': dispute_rate,
        'avg_response_minutes': avg_response_minutes,
        'streak': streak,
        'completed_count': completed_count,
        'dispute_count': dispute_count,
    }
