"""Data-retention policies (step 17).

Each policy names the data, how long it is kept, and why. `plan()` reports what is due for deletion (dry run);
`apply()` deletes it and records the counts in the audit log. A project on legal hold is never purged.
Run:  python -m app.security.retention            (dry run)
      python -m app.security.retention --apply    (delete)
or GET /admin/retention and POST /admin/retention/apply (admin only).
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, or_, select, text

from app.audit import record
from app.config import get_settings
from app.db import SessionLocal
from app.models import AuditLog, AuthSession, KbEmbeddingCache, LlmCall, Project, RetrievalLog, ReviewItem


def policies() -> list[dict]:
    s = get_settings()
    return [
        {"id": "auth_sessions", "data": "Expired or revoked sign-in sessions", "keep_days": s.retention_auth_sessions_days,
         "basis": "Security hygiene; session records are only needed for recent incident investigation"},
        {"id": "archived_projects", "data": "Archived projects: sources, requirements, artefacts, approvals, change "
                                            "requests, readiness reviews, members and workflow checkpoints",
         "keep_days": s.retention_project_after_archive_days,
         "basis": "Kept for a year after archiving for disputes and audits; never while on legal hold. Audit "
                  "events are kept separately (below)"},
        {"id": "review_queue", "data": "Resolved knowledge-base review items", "keep_days": s.retention_review_queue_days,
         "basis": "Evidence of human review of AI answers"},
        {"id": "embedding_cache", "data": "Cached embedding vectors", "keep_days": s.retention_embedding_cache_days,
         "basis": "Performance cache only; recomputed on demand"},
        {"id": "audit_log", "data": "Audit events", "keep_days": s.retention_audit_days,
         "basis": "Eight years, in line with record-keeping obligations for regulated lending (see the data-retention "
                  "policy in the knowledge base); events of projects on legal hold are kept"},
        {"id": "llm_calls", "data": "Prompts, model responses and token usage", "keep_days": s.retention_llm_calls_days,
         "basis": "Accountability record of what the AI was asked and answered; kept like audit events, and for "
                  "projects on legal hold"},
        {"id": "retrieval_log", "data": "Knowledge-base evidence retrieved by each agent", "keep_days": s.retention_llm_calls_days,
         "basis": "Shows which regulation and policy versions each recommendation relied on"},
    ]


def _cutoff(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _queries(session) -> dict:
    p = {x["id"]: x for x in policies()}
    held = select(Project.id).where(Project.legal_hold.is_(True))
    return {
        "auth_sessions": select(AuthSession.id).where(or_(AuthSession.expires_at < _cutoff(p["auth_sessions"]["keep_days"]),
                                                          AuthSession.revoked_at < _cutoff(p["auth_sessions"]["keep_days"]))),
        "archived_projects": select(Project.id).where(Project.archived_at < _cutoff(p["archived_projects"]["keep_days"]),
                                                      Project.legal_hold.is_(False)),
        "review_queue": select(ReviewItem.id).where(ReviewItem.status != "open",
                                                    ReviewItem.resolved_at < _cutoff(p["review_queue"]["keep_days"])),
        "embedding_cache": select(KbEmbeddingCache.content_sha256).where(
            KbEmbeddingCache.created_at < _cutoff(p["embedding_cache"]["keep_days"])),
        "audit_log": select(AuditLog.id).where(AuditLog.created_at < _cutoff(p["audit_log"]["keep_days"]),
                                               or_(AuditLog.project_ref.is_(None), AuditLog.project_ref.not_in(held))),
        "llm_calls": select(LlmCall.id).where(LlmCall.created_at < _cutoff(p["llm_calls"]["keep_days"]),
                                              or_(LlmCall.project_ref.is_(None), LlmCall.project_ref.not_in(held))),
        "retrieval_log": select(RetrievalLog.id).where(RetrievalLog.created_at < _cutoff(p["retrieval_log"]["keep_days"]),
                                                       or_(RetrievalLog.project_ref.is_(None), RetrievalLog.project_ref.not_in(held))),
    }


def plan() -> list[dict]:
    with SessionLocal() as session:
        due = {k: session.scalar(select(func.count()).select_from(q.subquery())) for k, q in _queries(session).items()}
        holds = session.scalar(select(func.count()).select_from(Project).where(Project.legal_hold.is_(True)))
    return [p | {"due": due[p["id"]], "projects_on_legal_hold": holds} for p in policies()]


def apply(actor: str = "retention") -> dict:
    deleted: dict[str, int] = {}
    with SessionLocal.begin() as session:
        q = _queries(session)
        projects = list(session.scalars(q["archived_projects"]))
        for pid in projects:  # workflow checkpoints live in LangGraph's tables, keyed by thread id
            for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                session.execute(text(f"DELETE FROM {table} WHERE thread_id = :t"), {"t": f"project-{pid}-v2"})
        deleted["archived_projects"] = session.execute(delete(Project).where(Project.id.in_(projects))).rowcount
        deleted["auth_sessions"] = session.execute(delete(AuthSession).where(AuthSession.id.in_(q["auth_sessions"]))).rowcount
        deleted["review_queue"] = session.execute(delete(ReviewItem).where(ReviewItem.id.in_(q["review_queue"]))).rowcount
        deleted["embedding_cache"] = session.execute(
            delete(KbEmbeddingCache).where(KbEmbeddingCache.content_sha256.in_(q["embedding_cache"]))).rowcount
        deleted["audit_log"] = session.execute(delete(AuditLog).where(AuditLog.id.in_(q["audit_log"]))).rowcount
        deleted["llm_calls"] = session.execute(delete(LlmCall).where(LlmCall.id.in_(q["llm_calls"]))).rowcount
        deleted["retrieval_log"] = session.execute(delete(RetrievalLog).where(RetrievalLog.id.in_(q["retrieval_log"]))).rowcount
    record(None, actor, "retention_applied", deleted)
    return deleted


if __name__ == "__main__":
    import json
    import sys

    from app.db import init_db
    init_db()
    print(json.dumps(apply("retention_cli") if "--apply" in sys.argv else plan(), indent=2, default=str))
