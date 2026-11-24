"""Audit logging (step 17): append-only and hash-chained, with the authenticated person behind every action.

Each event stores hash = SHA-256(previous hash + canonical JSON of the event). Changing, deleting or reordering any
past event breaks the chain from that point; `verify_chain()` (GET /admin/audit/verify) finds where.
Appends are serialised with a Postgres advisory lock so parallel agents cannot fork the chain.
"""

import hashlib
import json
from contextvars import ContextVar
from datetime import datetime, timezone

from sqlalchemy import select, text

from app.db import SessionLocal
from app.models import AuditLog

current_principal: ContextVar[str | None] = ContextVar("current_principal", default=None)
CHAIN_LOCK = 0x5245524144  # advisory lock id for the audit chain


def _digest(prev: str | None, project_id, actor, principal, action, detail, created_at: datetime) -> str:
    body = json.dumps({"project_id": project_id, "actor": actor, "principal": principal, "action": action,
                       "detail": detail, "at": created_at.astimezone(timezone.utc).isoformat()}, sort_keys=True, default=str)
    return hashlib.sha256(((prev or "") + body).encode()).hexdigest()


def record(project_id: int | None, actor: str, action: str, detail: dict | None = None) -> None:
    """Append an audit event. Every agent decision and human action goes through here."""
    detail = json.loads(json.dumps(detail or {}, default=str))  # store exactly what was hashed
    principal = current_principal.get()
    with SessionLocal.begin() as session:
        session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": CHAIN_LOCK})
        prev = session.scalar(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1))
        at = datetime.now(timezone.utc)
        session.add(AuditLog(project_id=project_id, project_ref=project_id, actor=actor[:100], principal=principal,
                             action=action, detail=detail,
                             created_at=at, prev_hash=prev,
                             hash=_digest(prev, project_id, actor[:100], principal, action, detail, at)))


def verify_chain() -> dict:
    """Recompute the chain. Events written before hash-chaining was enabled (hash NULL) are skipped."""
    with SessionLocal() as session:
        rows = session.scalars(select(AuditLog).where(AuditLog.hash.is_not(None)).order_by(AuditLog.id)).all()
    prev = None
    for i, r in enumerate(rows):
        # project_ref is the immutable copy: project_id becomes NULL if the project is later deleted
        expected = _digest(r.prev_hash, r.project_ref, r.actor, r.principal, r.action, r.detail, r.created_at)
        if r.hash != expected or (i and r.prev_hash != prev):
            return {"valid": False, "checked": i, "broken_at": r.id}
        prev = r.hash
    return {"valid": True, "checked": len(rows), "broken_at": None}
