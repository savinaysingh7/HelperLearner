"""Optional observability integrations (Sentry, etc.)."""

import logging

logger = logging.getLogger(__name__)


def configure_sentry(dsn, environment, traces_sample_rate=0.0, profiles_sample_rate=0.0):
    """Initialize Sentry if the SDK is installed and DSN is provided."""
    if not dsn:
        return False

    try:  # pragma: no cover - optional dependency
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
    except Exception as exc:
        logger.warning("Sentry DSN configured but sentry-sdk is unavailable: %s", exc)
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        traces_sample_rate=traces_sample_rate,
        profiles_sample_rate=profiles_sample_rate,
        integrations=[
            DjangoIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        send_default_pii=False,
    )
    logger.info("Sentry initialized for environment=%s", environment)
    return True
