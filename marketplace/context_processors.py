def active_experiments(request):
    """Expose active experiment assignments to templates."""
    return {
        'active_experiments': getattr(request, 'experiments', {}),
    }
