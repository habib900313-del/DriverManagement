"""Central activity-logging helper (single, maintainable entry point).

Every audit entry flows through :func:`log_activity`. It normalizes the actor,
extracts the client IP, strips sensitive values from every payload and writes
an append-only :class:`~apps.core.models.ActivityLog` row.

Design notes:

* Successful operations are logged *inside* the service/view transaction, so a
  rolled-back operation can never leave a misleading "success" entry.
* Failed operations are logged independently through :func:`log_activity_safe`,
  which never raises and uses a savepoint so an outer transaction stays usable.
* Sensitive keys (passwords, tokens, secrets, ...) are redacted recursively
  before the payload is persisted.
"""

from __future__ import annotations

import logging
import re
from ipaddress import ip_address as _parse_ip

from django.db import transaction

from .models import ActivityLog

logger = logging.getLogger(__name__)

REDACTED = "***"

# Key names that must never be persisted verbatim.
_SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|pwd|token|secret|api[_-]?key|apikey|authorization|"
    r"credential|otp|pin|cvv|private[_-]?key|session[_-]?key)",
    re.IGNORECASE,
)

_MAX_STRING = 500
_MAX_ITEMS = 100
_MAX_DEPTH = 4
_TRUNCATED = "…"


def _is_sensitive_key(key) -> bool:
    return bool(_SENSITIVE_KEY_RE.search(str(key)))


def sanitize_payload(value, depth: int = 0):
    """Return a JSON-safe copy of ``value`` with sensitive fields redacted.

    Handles nested dicts/lists, truncates very long strings and caps the number
    of rendered items so a single entry can never blow up the table.
    """
    if depth > _MAX_DEPTH:
        return _TRUNCATED
    if isinstance(value, dict):
        clean = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= _MAX_ITEMS:
                clean[_TRUNCATED] = f"{len(value) - _MAX_ITEMS} مورد دیگر"
                break
            if _is_sensitive_key(key):
                clean[str(key)] = REDACTED
            else:
                clean[str(key)] = sanitize_payload(item, depth + 1)
        return clean
    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)
        trimmed = [sanitize_payload(item, depth + 1) for item in items[:_MAX_ITEMS]]
        if len(items) > _MAX_ITEMS:
            trimmed.append(f"{_TRUNCATED} {len(items) - _MAX_ITEMS} مورد دیگر")
        return trimmed
    if isinstance(value, str):
        if len(value) <= _MAX_STRING:
            return value
        return value[:_MAX_STRING] + _TRUNCATED
    if value is None or isinstance(value, (bool, int, float)):
        return value
    # dates, Decimals, UUIDs and anything else -> readable string
    return str(value)


def client_ip(request):
    """Return the client IP from the request, or ``None`` when unavailable.

    Only ``REMOTE_ADDR`` is trusted: this app runs locally, and forwarded
    headers are attacker-controlled and must not be persisted as fact.
    """
    if request is None:
        return None
    address = (request.META.get("REMOTE_ADDR") or "").strip()
    if not address:
        return None
    try:
        _parse_ip(address)
    except ValueError:
        return None
    return address


def _resolve_actor(actor):
    """Return ``(actor_or_None, username_snapshot)`` for logging."""
    if actor is None:
        return None, "سیستم"
    is_authenticated = getattr(actor, "is_authenticated", False)
    get_username = getattr(actor, "get_username", None)
    username = get_username() if callable(get_username) else ""
    if not is_authenticated:
        # AnonymousUser (e.g. a failed login attempt).
        return None, username or "مهمان"
    return actor, username or "نامشخص"


def log_activity(
    *,
    action: str,
    module: str,
    actor=None,
    description: str = "",
    target_type: str = "",
    target_id=None,
    target_label: str = "",
    before_data=None,
    after_data=None,
    metadata=None,
    status: str = ActivityLog.Status.SUCCESS,
    request=None,
    ip_address=None,
) -> ActivityLog:
    """Persist a single audit entry.

    Exceptions propagate: call this inside the operation's transaction for
    successful actions so the log and the operation commit atomically.
    """
    actor_obj, actor_username = _resolve_actor(actor)
    resolved_ip = ip_address if ip_address is not None else client_ip(request)
    return ActivityLog.objects.create(
        actor=actor_obj,
        actor_username=actor_username,
        action=str(action)[:64],
        module=str(module)[:64],
        description=description or "",
        target_type=str(target_type or "")[:64],
        target_id=("" if target_id is None else str(target_id))[:64],
        target_label=(target_label or "")[:255],
        ip_address=resolved_ip,
        metadata=sanitize_payload(metadata) if metadata else {},
        before_data=sanitize_payload(before_data) if before_data is not None else None,
        after_data=sanitize_payload(after_data) if after_data is not None else None,
        status=status,
    )


def log_activity_safe(**kwargs) -> ActivityLog | None:
    """Write a log entry without ever breaking the caller.

    Used for independent records such as failed logins, where an audit-write
    failure must not change the request outcome. A savepoint keeps an outer
    transaction usable if the insert fails.
    """
    try:
        with transaction.atomic():
            return log_activity(**kwargs)
    except Exception:  # pragma: no cover - defensive
        logger.exception("ثبت گزارش فعالیت ناموفق بود.")
        return None
