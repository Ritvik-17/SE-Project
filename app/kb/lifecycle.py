"""Version control and authorisation: approve, reject, withdraw, supersede, and regulatory-change impact analysis."""

from datetime import date, datetime, timezone

from sqlalchemy import select

from app.audit import record
from app.db import SessionLocal
from app.kb.collections import COLLECTIONS
from app.kb.ingest import KbError
from app.models import Artifact, KbChunk, KbDocument, KbImpact


def _get(session, doc_id: int) -> KbDocument:
    doc = session.get(KbDocument, doc_id)
    if doc is None:
        raise KbError("Document not found")
    return doc


def approve(doc_id: int, approver: str, role: str) -> KbDocument:
    """Activate a draft. The previous in-force version is closed at the new version's effective date."""
    with SessionLocal.begin() as session:
        doc = _get(session, doc_id)
        if doc.status != "draft":
            raise KbError(f"Only drafts can be approved (status is {doc.status})")
        allowed = COLLECTIONS[doc.collection].approver_roles
        if role not in allowed:
            raise KbError(f"{doc.collection} items must be approved by one of {list(allowed)}")
        doc.status, doc.approved_by, doc.approved_role = "active", approver, role
        doc.approved_at = datetime.now(timezone.utc)
        superseded = []
        for old in session.scalars(select(KbDocument).where(
                KbDocument.doc_key == doc.doc_key, KbDocument.id != doc.id, KbDocument.status == "active")):
            if old.effective_from <= doc.effective_from:
                old.effective_to = doc.effective_from
                old.status = "superseded"
                superseded.append((old.id, old.version))
        result = {"doc_key": doc.doc_key, "version": doc.version, "superseded": [v for _, v in superseded]}
    record(None, approver, "kb_approved", result | {"role": role, "document_id": doc_id})
    for old_id, old_version in superseded:
        flag_impacts(old_id, result["doc_key"], old_version, result["version"], "superseded")
    with SessionLocal() as session:
        return _get(session, doc_id)


def reject(doc_id: int, reviewer: str, reason: str) -> None:
    with SessionLocal.begin() as session:
        doc = _get(session, doc_id)
        if doc.status != "draft":
            raise KbError("Only drafts can be rejected")
        doc.status, doc.notes = "rejected", reason
    record(None, reviewer, "kb_rejected", {"document_id": doc_id, "reason": reason})


def withdraw(doc_id: int, actor: str, reason: str) -> None:
    with SessionLocal.begin() as session:
        doc = _get(session, doc_id)
        if doc.status != "active":
            raise KbError("Only active documents can be withdrawn")
        doc.status, doc.effective_to, doc.notes = "withdrawn", date.today(), reason
        key, version = doc.doc_key, doc.version
    record(None, actor, "kb_withdrawn", {"document_id": doc_id, "reason": reason})
    flag_impacts(doc_id, key, version, None, "withdrawn")


def flag_impacts(doc_id: int, doc_key: str, old_version: str, new_version: str | None, change: str) -> int:
    """Find projects whose generated artefacts cite passages of the changed version and flag them for re-evaluation."""
    with SessionLocal() as session:
        refs = {f"KB-{cid}" for cid in session.scalars(select(KbChunk.id).where(KbChunk.document_id == doc_id))}
        artifacts = session.scalars(select(Artifact).where(Artifact.kind == "compliance_matrix", Artifact.superseded_at.is_(None))).all()
        hits = {}
        for a in artifacts:
            cited = sorted({m.get("evidence_ref") for m in a.content["data"].get("mappings", [])} & refs)
            if cited:
                hits[a.project_id] = cited
    if not hits:
        return 0
    with SessionLocal.begin() as session:
        for pid, cited in hits.items():
            session.add(KbImpact(project_id=pid, doc_key=doc_key, old_version=old_version, new_version=new_version,
                                 change=change, cited_refs=cited))
    for pid, cited in hits.items():
        record(pid, "kb_lifecycle", "regulatory_change_impact",
               {"doc_key": doc_key, "old_version": old_version, "new_version": new_version, "change": change, "refs": cited})
    return len(hits)
