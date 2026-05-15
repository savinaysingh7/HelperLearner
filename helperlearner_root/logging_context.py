"""Request-scoped logging context helpers."""

import contextvars
import logging

_request_id_var = contextvars.ContextVar("request_id", default="-")
_request_path_var = contextvars.ContextVar("request_path", default="-")
_request_method_var = contextvars.ContextVar("request_method", default="-")
_request_user_var = contextvars.ContextVar("request_user", default="-")


def set_request_context(request_id="-", request_path="-", request_method="-", request_user="-"):
    """Set request-scoped logging context and return reset tokens."""
    return {
        "request_id": _request_id_var.set(request_id or "-"),
        "request_path": _request_path_var.set(request_path or "-"),
        "request_method": _request_method_var.set(request_method or "-"),
        "request_user": _request_user_var.set(request_user or "-"),
    }


def update_request_user(request_user="-"):
    """Update request user context after authentication is available."""
    return _request_user_var.set(request_user or "-")


def reset_request_context(tokens):
    """Reset request-scoped logging context using prior tokens."""
    if not tokens:
        return
    if "request_id" in tokens:
        _request_id_var.reset(tokens["request_id"])
    if "request_path" in tokens:
        _request_path_var.reset(tokens["request_path"])
    if "request_method" in tokens:
        _request_method_var.reset(tokens["request_method"])
    if "request_user" in tokens:
        _request_user_var.reset(tokens["request_user"])


class RequestContextFilter(logging.Filter):
    """Inject request-scoped fields into every log record."""

    def filter(self, record):
        record.request_id = _request_id_var.get()
        record.request_path = _request_path_var.get()
        record.request_method = _request_method_var.get()
        record.request_user = _request_user_var.get()
        return True
