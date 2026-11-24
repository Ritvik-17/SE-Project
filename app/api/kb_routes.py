"""Knowledge-base API (problem statement steps 5-6): submit versions, approve, browse, diff, search, impacts."""

import json
from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select

from app.catalog.loader import get_catalog
from app.db import SessionLocal
from app.ingestion.parsers import extract_text
from app.kb import lifecycle
from app.kb.collections import AGENT_ALLOWLIST, COLLECTIONS, JURISDICTIONS, LICENSES
from app.kb.ingest import ItemMetadata, section_diff, submit
from app.kb.lookup import glossary, terms_in
from app.kb.retrieval import search
from app.models import KbChunk, KbDocument, KbImpact
from app.security import rbac


def _approver_of(request: Request, doc_id: int) -> str:
    """Rejecting or withdrawing needs one of the item's collection approver roles on the user's account."""
    with SessionLocal() as session:
        doc = session.get(KbDocument, doc_id)
        if doc is None:
            raise HTTPException(404, "Document not found")
        roles = COLLECTIONS[doc.collection].approver_roles
    me = rbac.principal(request)
    if not set(me.roles) & set(roles):
        raise HTTPException(403, f"Requires one of the approver roles of this collection: {', '.join(roles)}")
    return me.username

router = APIRouter(prefix="/kb", tags=["knowledge base"])


def doc_out(d: KbDocument, today: date | None = None) -> dict:
    today = today or date.today()
    in_force = d.status in ("active", "superseded") and d.effective_from <= today and (d.effective_to is None or d.effective_to > today)
    return {
        "id": d.id, "doc_key": d.doc_key, "version": d.version, "collection": d.collection, "title": d.title,
        "source": {"issuer": d.issuer, "url": d.source_url, "license": d.license, "sha256": d.content_sha256},
        "jurisdictions": d.jurisdictions, "effective_from": d.effective_from.isoformat(),
        "effective_to": d.effective_to.isoformat() if d.effective_to else None,
        "review_due": d.review_due.isoformat() if d.review_due else None,
        "review_overdue": bool(d.review_due and d.review_due < today and in_force),
        "applicability": d.applicability, "status": d.status, "in_force": in_force,
        "submitted_by": d.submitted_by, "approved_by": d.approved_by, "approved_role": d.approved_role,
        "approved_at": d.approved_at.isoformat() if d.approved_at else None,
        "section_count": d.section_count, "chunk_count": d.chunk_count, "embedding_model": d.embedding_model,
        "redactions": d.redactions, "notes": d.notes, "created_at": d.created_at.isoformat(),
    }


@router.get("/meta")
def meta():
    return {
        "collections": [{"id": c.id, "name": c.name, "description": c.description, "approver_roles": list(c.approver_roles),
                         "searchable": c.searchable, "chunking": c.chunking} for c in COLLECTIONS.values()],
        "licenses": list(LICENSES), "jurisdictions": JURISDICTIONS,
        "agent_allowlist": {k: list(v) for k, v in AGENT_ALLOWLIST.items()},
    }


@router.get("/documents")
def list_documents(collection: str | None = None, status: str | None = None):
    with SessionLocal() as session:
        q = select(KbDocument).order_by(KbDocument.collection, KbDocument.doc_key, KbDocument.effective_from.desc())
        if collection:
            q = q.where(KbDocument.collection == collection)
        if status:
            q = q.where(KbDocument.status == status)
        return [doc_out(d) for d in session.scalars(q)]


@router.post("/documents")
async def submit_document(request: Request, metadata: str = Form(..., description="JSON matching ItemMetadata"),
                          submitted_by: str = Form(""), content: str | None = Form(None),
                          file: UploadFile | None = File(None)):
    """Submit a new item or a new version as a DRAFT. Source, jurisdiction, effective date, version and
    applicability are mandatory."""
    try:
        meta_obj = ItemMetadata.model_validate(json.loads(metadata))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(422, f"Invalid metadata: {exc}")
    if file is not None and file.filename:
        text = extract_text(file.filename, await file.read())
    elif content:
        text = content
    else:
        raise HTTPException(422, "Provide either 'content' or 'file'")
    doc, diff = submit(meta_obj, text, rbac.principal(request).username)  # the signed-in user, not a typed name
    return {"document": doc_out(doc), "diff": diff}


@router.get("/documents/{doc_id}")
def get_document(doc_id: int):
    with SessionLocal() as session:
        d = session.get(KbDocument, doc_id)
        if d is None:
            raise HTTPException(404, "Document not found")
        versions = session.scalars(select(KbDocument).where(KbDocument.doc_key == d.doc_key)
                                   .order_by(KbDocument.effective_from.desc(), KbDocument.id.desc())).all()
        previous = next((v for v in versions if v.id != d.id and v.status in ("active", "superseded")
                         and v.effective_from <= d.effective_from), None)
        sections = session.execute(select(KbChunk.section_path, KbChunk.clause_ref, func.count())
                                   .where(KbChunk.document_id == d.id, KbChunk.kind == "child")
                                   .group_by(KbChunk.section_path, KbChunk.clause_ref)).all()
        return {
            "document": doc_out(d), "content": d.content,
            "versions": [doc_out(v) for v in versions],
            "diff_vs": previous.version if previous else None,
            "diff": section_diff(previous.content if previous else None, d.content),
            "sections": [{"path": p, "clause_ref": c, "passages": n} for p, c, n in sections],
        }


class Decision(BaseModel):
    actor: str = ""  # ignored: the signed-in user is recorded
    role: str | None = None
    reason: str = ""


@router.post("/documents/{doc_id}/approve")
def approve(doc_id: int, body: Decision, request: Request):
    if not body.role or get_catalog().role(body.role) is None:
        raise HTTPException(422, "A valid approver role is required")
    me = rbac.acting_as(request, body.role)
    return doc_out(lifecycle.approve(doc_id, me.username, body.role))


@router.post("/documents/{doc_id}/reject")
def reject(doc_id: int, body: Decision, request: Request):
    lifecycle.reject(doc_id, _approver_of(request, doc_id), body.reason or "rejected")
    return {"ok": True}


@router.post("/documents/{doc_id}/withdraw")
def withdraw(doc_id: int, body: Decision, request: Request):
    if not body.reason.strip():
        raise HTTPException(422, "A reason is required to withdraw a document")
    lifecycle.withdraw(doc_id, _approver_of(request, doc_id), body.reason)
    return {"ok": True}


class AskRequest(BaseModel):
    question: str
    asked_by: str
    domain: str = "loan_processing"
    jurisdiction: str = "IN"
    project_id: int | None = None
    as_of: date | None = None


@router.post("/ask")
def ask(body: AskRequest, request: Request):
    """Stakeholder question → classify → retrieve → grounded answer with citations and confidence → escalate if weak."""
    from app.kb.grounding import ground_answer
    from app.security.masking import mask
    if len(body.question.strip()) < 5:
        raise HTTPException(422, "Ask a complete question")
    from app.security.filters import neutralise
    question, _ = neutralise(mask(body.question).text)
    if body.project_id is not None and not rbac.is_member(rbac.principal(request), body.project_id):
        raise HTTPException(404, "Project not found")
    return ground_answer(question, domain=body.domain, jurisdiction=body.jurisdiction,
                         asked_by=rbac.principal(request).username, project_id=body.project_id, as_of=body.as_of)


@router.get("/review-queue")
def review_queue(status: str = "open"):
    from app.models import ReviewItem
    with SessionLocal() as session:
        rows = session.scalars(select(ReviewItem).where(ReviewItem.status == status).order_by(ReviewItem.id.desc())).all()
        return [{"id": r.id, "project_id": r.project_id, "kind": r.kind, "subject": r.subject, "payload": r.payload,
                 "reasons": r.reasons, "requested_by": r.requested_by, "status": r.status, "resolution": r.resolution,
                 "resolved_by": r.resolved_by, "created_at": r.created_at.isoformat()} for r in rows]


class Resolution(BaseModel):
    actor: str = ""  # ignored: the signed-in user is recorded
    role: str
    outcome: str  # confirmed | corrected | dismissed
    resolution: str = ""


@router.post("/review-queue/{item_id}/resolve")
def resolve_review(item_id: int, body: Resolution, request: Request):
    from datetime import datetime, timezone

    from app.audit import record
    from app.models import ReviewItem
    if body.outcome not in ("confirmed", "corrected", "dismissed"):
        raise HTTPException(422, "outcome must be confirmed, corrected or dismissed")
    if body.outcome == "corrected" and not body.resolution.strip():
        raise HTTPException(422, "Provide the corrected answer")
    if get_catalog().role(body.role) is None:
        raise HTTPException(422, "A valid reviewer role is required")
    body.actor = rbac.acting_as(request, body.role).username
    with SessionLocal.begin() as session:
        item = session.get(ReviewItem, item_id)
        if item is None:
            raise HTTPException(404, "Review item not found")
        if item.status != "open":
            raise HTTPException(409, "Already resolved")
        item.status, item.resolution = body.outcome, body.resolution or None
        item.resolved_by, item.resolved_role, item.resolved_at = body.actor, body.role, datetime.now(timezone.utc)
        project_id = item.project_id
    record(project_id, body.actor, f"review_{body.outcome}", {"review_id": item_id, "role": body.role})
    return {"ok": True}


class SearchRequest(BaseModel):
    query: str
    collections: list[str] | None = None
    domain: str | None = None
    jurisdiction: str | None = None
    as_of: date | None = None
    k: int = 8


@router.post("/search")
def search_kb(body: SearchRequest):
    """Retrieval exactly as agents run it, with per-stage scores (vector rank, lexical rank, RRF, rerank)."""
    hits = search(body.query, agent="kb_explorer", collections=body.collections, domain=body.domain,
                  jurisdiction=body.jurisdiction, as_of=body.as_of, k=body.k)
    return [h.to_dict() for h in hits]


@router.get("/glossary")
def get_glossary(text: str | None = None):
    terms = glossary()
    if text:
        found, undefined = terms_in(text, terms)
        return {"defined": found, "undefined": undefined}
    unique = {id(v): v for v in terms.values()}
    return sorted(unique.values(), key=lambda t: t["term"].lower())


@router.get("/impacts")
def impacts(project_id: int | None = None, status: str = "open"):
    with SessionLocal() as session:
        q = select(KbImpact).where(KbImpact.status == status).order_by(KbImpact.id.desc())
        if project_id:
            q = q.where(KbImpact.project_id == project_id)
        return [{"id": i.id, "project_id": i.project_id, "doc_key": i.doc_key, "old_version": i.old_version,
                 "new_version": i.new_version, "change": i.change, "cited_refs": i.cited_refs,
                 "created_at": i.created_at.isoformat()} for i in session.scalars(q)]


@router.post("/impacts/{impact_id}/resolve")
def resolve_impact(impact_id: int, body: Decision):
    with SessionLocal.begin() as session:
        i = session.get(KbImpact, impact_id)
        if i is None:
            raise HTTPException(404, "Impact not found")
        i.status = "resolved"
    from app.audit import record
    record(i.project_id, body.actor, "regulatory_impact_resolved", {"impact_id": impact_id, "reason": body.reason})
    return {"ok": True}
