"""Role-based access control for the Lab Tech Portal.

Slice A, Issue #44 — RBAC tiers.
Slice B, Issue #63 — enforce mode (audit log landed in #46).

Pattern: docs/patterns/auth/multi-mode-auth.md
(qe-architecture-ai-assisted-guide — SHA at branch creation: 5f11523)

Okta groups are mapped to internal tiers via environment variables:

    RBAC_ADMIN_GROUPS          — comma-separated Okta group names for 'admin'
    RBAC_LAB_TECH_LEAD_GROUPS  — for 'lab-tech-lead'
    RBAC_LAB_TECH_GROUPS       — for 'lab-tech'

Any authenticated user not matching a group is assigned the 'viewer' tier.

RBAC enforcement is now always active (abort 403 on role mismatch).
The old warn-only escape hatch has been removed.  Denied requests are
recorded to the shared audit log via services/audit_log.log_event().
"""
from __future__ import annotations

from functools import wraps
from typing import Callable, Iterable

from flask import abort, current_app, request, session

# Pattern: docs/patterns/observability/audit-logging.md
# (qe-architecture-ai-assisted-guide @ 567edc9)
# NOTE(guide-friction F05): audit-logging.md does not address structlog; see
# docs/guide-friction.md entry F05 for the gap report.
from services.logging_config import get_logger

logger = get_logger(__name__)

# Ordered from most-privileged to least.
TIERS = ("admin", "lab-tech-lead", "lab-tech", "viewer")

# Numeric rank: lower = more privileged.
_TIER_RANK: dict[str, int] = {tier: i for i, tier in enumerate(TIERS)}


def _parse_group_list(raw: str) -> list[str]:
    """Split a comma-separated group list; strip whitespace; drop empties."""
    return [g.strip() for g in raw.split(",") if g.strip()]


def get_user_tier(groups: Iterable[str]) -> str:
    """Map a set of Okta group names to the most-privileged matching tier.

    Falls back to 'viewer' when no configured group matches.

    Args:
        groups: The Okta groups claim for the current user.

    Returns:
        One of 'admin', 'lab-tech-lead', 'lab-tech', or 'viewer'.
    """
    group_set = set(groups)
    cfg = current_app.config

    tier_env_map = (
        ("admin", cfg.get("RBAC_ADMIN_GROUPS", "")),
        ("lab-tech-lead", cfg.get("RBAC_LAB_TECH_LEAD_GROUPS", "")),
        ("lab-tech", cfg.get("RBAC_LAB_TECH_GROUPS", "")),
    )
    for tier, raw in tier_env_map:
        configured = _parse_group_list(raw)
        if configured and group_set.intersection(configured):
            return tier

    return "viewer"


def requires_role(role: str) -> Callable:
    """Decorator that enforces a minimum role tier on a view function.

    Raises 403 when the authenticated user's tier is below the required
    role.  Every denial is recorded to the shared audit log.

    Raises:
        ValueError: at decoration time if ``role`` is not a known tier.
            This is a fail-fast guard so a typo'd ``@requires_role('Admin')``
            cannot silently degrade to a permissive lookup.

    Usage::

        @systems_bp.post("/<int:system_id>/hard-delete")
        @requires_role("admin")
        def hard_delete_system(system_id: int):
            ...
    """
    if role not in _TIER_RANK:
        raise ValueError(
            f"requires_role: unknown role {role!r}. "
            f"Valid roles (highest → lowest): {TIERS}"
        )

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapped(*args, **kwargs):
            login_disabled = current_app.config.get("LOGIN_DISABLED", False)

            if login_disabled:
                # Dev/test mode with auth disabled — skip RBAC entirely.
                return fn(*args, **kwargs)

            identity = session.get("user_identity", {})
            user_groups: list[str] = identity.get("groups", [])
            user_tier = get_user_tier(user_groups)
            # role is validated above at decoration time; user_tier is always
            # one of TIERS (get_user_tier defaults to 'viewer').
            required_rank = _TIER_RANK[role]
            user_rank = _TIER_RANK[user_tier]

            if user_rank > required_rank:
                actor = identity.get("email", "<unknown>")
                endpoint = request.endpoint or request.path
                # Emit structured log.
                logger.warning(
                    "rbac_denial",
                    user=actor,
                    tier=user_tier,
                    required=role,
                    endpoint=endpoint,
                    path=request.path,
                )
                # Record denial in the shared audit log (circular-import-safe:
                # audit_log does not import rbac).
                try:
                    from services.audit_log import log_event as _audit_log_event
                    _audit_log_event(
                        actor=actor,
                        action="rbac.denial",
                        resource_type="endpoint",
                        resource_id=endpoint,
                        detail={"required": role, "user_tier": user_tier},
                    )
                except Exception:  # noqa: BLE001 — audit failure must not mask 403
                    pass
                abort(403)

            return fn(*args, **kwargs)

        return wrapped

    return decorator
