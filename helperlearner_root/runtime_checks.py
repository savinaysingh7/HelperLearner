"""Runtime diagnostics helpers used by ops views and management commands."""

from importlib.util import find_spec
from pathlib import Path
from urllib.parse import urlsplit
import uuid

from django.conf import settings
from django.core.cache import caches
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


def _make_check(ok, detail, critical=False):
    """Build a standardized runtime check payload item."""
    return {
        "ok": bool(ok),
        "critical": bool(critical),
        "detail": detail,
    }


def _check_database():
    """Validate default database connectivity with a lightweight query."""
    try:
        connection = connections[DEFAULT_DB_ALIAS]
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return _make_check(True, "Database connection OK.", critical=True)
    except Exception as exc:  # pragma: no cover - depends on runtime infrastructure
        return _make_check(False, f"Database connection failed: {exc}", critical=True)


def _check_cache():
    """Validate cache backend read/write behavior."""
    cache = caches["default"]
    test_key = f"ops:runtime:{uuid.uuid4().hex}"
    try:
        cache.set(test_key, "ok", timeout=30)
        cached_value = cache.get(test_key)
        cache.delete(test_key)
        if cached_value != "ok":
            return _make_check(False, "Cache returned an unexpected value.", critical=True)
        return _make_check(True, "Cache read/write OK.", critical=True)
    except Exception as exc:  # pragma: no cover - depends on runtime infrastructure
        return _make_check(False, f"Cache operation failed: {exc}", critical=True)


def _check_migrations():
    """Report unapplied migrations count for the default database."""
    try:
        connection = connections[DEFAULT_DB_ALIAS]
        executor = MigrationExecutor(connection)
        pending_plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        pending_count = len(pending_plan)
        if pending_count:
            return _make_check(False, f"{pending_count} unapplied migration(s) detected.", critical=False)
        return _make_check(True, "No pending migrations.", critical=False)
    except Exception as exc:  # pragma: no cover - depends on runtime infrastructure
        return _make_check(False, f"Migration state check failed: {exc}", critical=False)


def _check_channels():
    """Check channels/websocket availability based on installation and layer."""
    channels_installed = find_spec("channels") is not None and "channels" in settings.INSTALLED_APPS
    if not channels_installed:
        return _make_check(False, "Channels is not installed/enabled; websocket realtime is disabled.", critical=False)

    try:
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        if channel_layer is None:
            return _make_check(False, "Channel layer is unavailable.", critical=False)
        layer_name = channel_layer.__class__.__name__
        return _make_check(True, f"Channels enabled ({layer_name}).", critical=False)
    except Exception as exc:  # pragma: no cover - depends on optional dependency
        return _make_check(False, f"Channels check failed: {exc}", critical=False)


def _check_celery():
    """Check celery broker configuration shape."""
    broker_url = (getattr(settings, "CELERY_BROKER_URL", "") or "").strip()
    if not broker_url:
        return _make_check(False, "CELERY_BROKER_URL is empty.", critical=False)

    parsed = urlsplit(broker_url)
    if not parsed.scheme:
        return _make_check(False, "CELERY_BROKER_URL is not a valid URL.", critical=False)
    return _make_check(True, f"Celery broker configured ({parsed.scheme}).", critical=False)


def _check_ai_assist():
    """Check AI assistant configuration presence."""
    api_key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if not api_key:
        return _make_check(False, "GEMINI_API_KEY is not configured; AI assist is disabled.", critical=False)
    return _make_check(True, "AI assistant credentials configured.", critical=False)


def _check_logging_file():
    """Check server log file path parent exists and is writable."""
    file_handler = (getattr(settings, "LOGGING", {}) or {}).get("handlers", {}).get("file", {})
    file_name = file_handler.get("filename")
    if not file_name:
        return _make_check(False, "File logger is not configured.", critical=False)

    path = Path(file_name)
    parent = path.parent
    if not parent.exists():
        return _make_check(False, f"Log directory does not exist: {parent}", critical=False)
    try:
        with path.open("a", encoding="utf-8"):
            pass
        return _make_check(True, f"Log file writable: {path}", critical=False)
    except Exception as exc:  # pragma: no cover - depends on filesystem permissions
        return _make_check(False, f"Log file is not writable: {exc}", critical=False)


def collect_runtime_snapshot():
    """Collect a consolidated runtime health snapshot."""
    checks = {
        "database": _check_database(),
        "cache": _check_cache(),
        "migrations": _check_migrations(),
        "channels": _check_channels(),
        "celery": _check_celery(),
        "ai_assist": _check_ai_assist(),
        "logging": _check_logging_file(),
    }

    critical_failures = [name for name, item in checks.items() if item["critical"] and not item["ok"]]
    warnings = [name for name, item in checks.items() if not item["ok"] and not item["critical"]]

    if critical_failures:
        status = "degraded"
    elif warnings:
        status = "warning"
    else:
        status = "healthy"

    return {
        "status": status,
        "healthy": not critical_failures,
        "critical_failures": critical_failures,
        "warnings": warnings,
        "checks": checks,
        "environment": {
            "debug": bool(getattr(settings, "DEBUG", False)),
            "database_engine": settings.DATABASES["default"].get("ENGINE", ""),
            "cache_backend": settings.CACHES["default"].get("BACKEND", ""),
            "timezone": settings.TIME_ZONE,
        },
        "checked_at": timezone.now().isoformat(),
    }

