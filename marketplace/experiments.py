import hashlib

from .models import Experiment, ExperimentAssignment


def _stable_percent(seed_text):
    digest = hashlib.sha256(seed_text.encode('utf-8')).hexdigest()
    return int(digest[:8], 16) % 100


def _pick_variant(experiment, seed_text):
    variants = list(experiment.variants.all().order_by('id'))
    if not variants:
        return None

    total_weight = sum(variant.weight for variant in variants)
    if total_weight <= 0:
        return variants[0]

    bucket = int(hashlib.sha256((seed_text + '|variant').encode('utf-8')).hexdigest()[:8], 16) % total_weight
    running = 0
    for variant in variants:
        running += variant.weight
        if bucket < running:
            return variant
    return variants[-1]


def assign_active_experiments(request):
    """Assign active A/B experiments for the request and persist deterministic variants."""
    if not hasattr(request, 'session'):
        request.experiments = {}
        return {}

    if not request.session.session_key:
        request.session.save()

    session_key = request.session.session_key or ''
    identity = f'user:{request.user.pk}' if request.user.is_authenticated else f'session:{session_key}'

    experiments = [exp for exp in Experiment.objects.prefetch_related('variants').filter(is_active=True) if exp.is_live()]
    if not experiments:
        request.experiments = {}
        return {}

    experiment_ids = [exp.pk for exp in experiments]

    # Batch-fetch existing assignments to avoid N+1
    existing_assignments = {}
    if request.user.is_authenticated:
        for assignment in ExperimentAssignment.objects.filter(
            experiment_id__in=experiment_ids, user=request.user
        ).select_related('variant', 'experiment'):
            existing_assignments[assignment.experiment_id] = assignment

    session_assignments = {}
    if session_key:
        for assignment in ExperimentAssignment.objects.filter(
            experiment_id__in=experiment_ids, user__isnull=True, session_key=session_key
        ).select_related('variant', 'experiment'):
            session_assignments.setdefault(assignment.experiment_id, assignment)

    assignments = {}
    for experiment in experiments:
        assignment = existing_assignments.get(experiment.pk)
        if assignment is None:
            assignment = session_assignments.get(experiment.pk)

        if assignment is None:
            traffic_bucket = _stable_percent(f'{experiment.slug}:{identity}')
            if traffic_bucket < experiment.traffic_percentage:
                chosen_variant = _pick_variant(experiment, f'{experiment.slug}:{identity}')
                if chosen_variant:
                    assignment = ExperimentAssignment.objects.create(
                        experiment=experiment,
                        variant=chosen_variant,
                        user=request.user if request.user.is_authenticated else None,
                        session_key='' if request.user.is_authenticated else session_key,
                    )

        assignments[experiment.slug] = assignment.variant.key if assignment else 'control'

    request.experiments = assignments
    return assignments
