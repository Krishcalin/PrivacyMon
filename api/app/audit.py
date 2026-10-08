"""Append-only audit trail writer (SRS FR-8.3 / NFR-9).

Every create, update, review, approve, export and credential use should leave an
immutable ``audit_log`` row with the actor, the action, the object, and the before/after
state. The table is append-only — a database trigger rejects UPDATE and DELETE — so this
module only ever INSERTs.

`record` is deliberately defensive: an audit failure must never roll back or mask the
primary action, so it swallows its own errors (the caller's transaction is untouched).
Pass the SAME session the primary write uses so the audit row commits atomically with it.
"""
from __future__ import annotations

import uuid
from typing import Any

from platform_db.models.platform_tables import AuditLog


def _jsonable(value: Any) -> Any:
    """Coerce a before/after snapshot into JSON-storable primitives."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    return str(value)


def record(
    session,
    *,
    actor_id: uuid.UUID | None,
    action: str,
    object_type: str,
    object_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    ip: str | None = None,
    request_id: str | None = None,
) -> None:
    """Append one audit row on ``session`` (committed by the caller). Never raises.

    ``action`` is a dotted verb such as ``finding.review`` or ``inventory.update``;
    ``object_type``/``object_id`` identify the row; ``before``/``after`` capture the
    change (coerced to JSON-safe values and stored in the append-only log)."""
    try:
        session.add(AuditLog(
            actor_id=actor_id,
            action=action,
            object_type=object_type,
            object_id=str(object_id) if object_id is not None else None,
            before=_jsonable(before) if before is not None else None,
            after=_jsonable(after) if after is not None else None,
            ip=ip,
            request_id=request_id,
        ))
        session.flush()
    except Exception:  # noqa: BLE001 — auditing must never break the primary action
        pass
