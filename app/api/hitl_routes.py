"""Human-in-the-loop API (step 16): control register, change requests, artefact regeneration, readiness reviews.

The in-graph gates (clarification, baseline, SDLC, workflow) are answered through POST /projects/{id}/decision.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import llm
from app.audit import record
from app.catalog.loader import get_catalog
from app.db import get_session
from app.hitl import changes, readiness
from app.hitl.controls import register
from app.models import ApprovalRequest, Project
from app.security import rbac
from app.security.masking import mask

router = APIRouter(prefix="/projects/{project_id}", tags=["human-in-the-loop"])


class ChangeProposal(BaseModel):
    requested_by: str = Field(min_length=1)
    role: str
    action: Literal["add", "modify", "remove"]
    req_id: str | None = None
    statement: str | None = None
    reason: str = Field(min_length=3)
    categories: list[str] = []
    priority: Literal["must", "should", "could"] = "should"
    type: Literal["functional", "non_functional"] = "functional"


class ChangeDecision(BaseModel):
    reviewer: str = Field(min_length=1)
    reviewer_role: str
    decision: Literal["approve", "reject", "request_changes"]
    comment: str = ""


class ChangeRevision(BaseModel):
    requested_by: str = Field(min_length=1)
    statement: str = Field(min_length=3)
    reason: str = ""


class ReadinessOpen(BaseModel):
    requested_by: str = Field(min_length=1)
    role: str
    release: str = Field(min_length=1, max_length=120)


class ReadinessDecision(BaseModel):
    reviewer: str = Field(min_length=1)
    reviewer_role: str
    decision: Literal["go", "conditional", "no_go"]
    comment: str = ""
    attest: list[str] = []
    waivers: dict[str, str] = {}


class Regenerate(BaseModel):
    requested_by: str = Field(min_length=1)
    role: str


def _m(text: str | None) -> str | None:
    return mask(text).text if text and text.strip() else text


def _project(session: Session, project_id: int) -> Project:
    p = session.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


def _request(session: Session, project_id: int, rid: int, kind: str) -> ApprovalRequest:
    r = session.get(ApprovalRequest, rid)
    if not r or r.project_id != project_id or r.kind != kind:
        raise HTTPException(404, "Not found")
    return r


def _out(r: ApprovalRequest) -> dict:
    out = {"id": r.id, "kind": r.kind, "title": r.title, "payload": r.payload, "required_roles": r.required_roles,
           "decisions": r.decisions, "status": r.status, "created_by": r.created_by, "created_role": r.created_role,
           "created_at": r.created_at.isoformat() if r.created_at else None,
           "closed_at": r.closed_at.isoformat() if r.closed_at else None}
    if r.kind == "change_request":
        latest = changes.current_decisions(r)
        out["pending_roles"] = [x for x in r.required_roles if latest.get(x, {}).get("decision") != "approve"]
    else:
        latest = {d["role"]: d["decision"] for d in r.decisions}
        out["pending_roles"] = [x for x in r.required_roles if x not in latest]
    return out


def _guard(fn):
    try:
        return fn()
    except changes.ChangeError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/hitl")
def hitl_register(project_id: int, request: Request, session: Session = Depends(get_session)):
    """Every human-in-the-loop control for this project, with its status and evidence."""
    _project(session, project_id)
    state = request.app.state.graph.get_state(changes.graph_config(project_id)).values or {}
    reqs = session.scalars(select(ApprovalRequest).where(ApprovalRequest.project_id == project_id)
                           .order_by(ApprovalRequest.id)).all()
    return register(state, [_out(r) for r in reqs])


# ---------- Changes to approved requirements ----------

@router.get("/change-requests")
def list_changes(project_id: int, session: Session = Depends(get_session)):
    rows = session.scalars(select(ApprovalRequest).where(ApprovalRequest.project_id == project_id,
                                                         ApprovalRequest.kind == "change_request").order_by(ApprovalRequest.id)).all()
    return [_out(r) for r in rows]


@router.post("/change-requests")
def propose_change(project_id: int, body: ChangeProposal, request: Request, session: Session = Depends(get_session)):
    _project(session, project_id)
    me = rbac.acting_as(request, body.role)
    data = body.model_dump() | {"statement": _m(body.statement), "reason": _m(body.reason), "requested_by": me.username}
    cr = _guard(lambda: changes.propose(session, request.app.state.graph, project_id, data))
    session.commit()
    return _out(cr)


@router.post("/change-requests/{cr_id}/decision")
def decide_change(project_id: int, cr_id: int, body: ChangeDecision, request: Request, session: Session = Depends(get_session)):
    cr = _request(session, project_id, cr_id, "change_request")
    me = rbac.acting_as(request, body.reviewer_role)
    _guard(lambda: changes.decide(session, request.app.state.graph, cr, me.username, body.reviewer_role, body.decision,
                                  _m(body.comment) or ""))
    session.commit()
    return _out(cr)


@router.post("/change-requests/{cr_id}/revise")
def revise_change(project_id: int, cr_id: int, body: ChangeRevision, request: Request,
                  session: Session = Depends(get_session)):
    cr = _request(session, project_id, cr_id, "change_request")
    me = rbac.principal(request)
    if me.username != cr.created_by and not me.is_admin:
        raise HTTPException(403, "Only the proposer can revise a change request")
    _guard(lambda: changes.revise(cr, _m(body.statement), _m(body.reason), me.username))
    session.commit()
    return _out(cr)


@router.post("/artifacts/regenerate")
def regenerate_artifacts(project_id: int, body: Regenerate, request: Request, session: Session = Depends(get_session)):
    """Regenerate the documents from the current (changed) baseline. A human asks for it; it is never automatic."""
    project = _project(session, project_id)
    if get_catalog().role(body.role) is None:
        raise HTTPException(422, f"Unknown role '{body.role}'")
    body.requested_by = rbac.acting_as(request, body.role).username
    llm.get_model()  # fail fast without an LLM
    graph = request.app.state.graph
    state = _guard(lambda: changes.completed_state(graph, project_id))
    from app.agents.documentation import documentation
    if project.status != "artifacts_stale":
        raise HTTPException(409, "Documents are already up to date")
    session.close()  # the documentation agent writes artefacts in its own transaction
    out = documentation(state)  # requirements table rows were already updated when the change was applied
    graph.update_state(changes.graph_config(project_id), out, as_node="documentation")
    record(project_id, body.requested_by, "artifacts_regenerated", {"role": body.role})
    return {"status": "completed", "artifacts": sorted(out["artifacts"])}


# ---------- Production readiness ----------

@router.get("/readiness-reviews")
def list_reviews(project_id: int, session: Session = Depends(get_session)):
    rows = session.scalars(select(ApprovalRequest).where(ApprovalRequest.project_id == project_id,
                                                         ApprovalRequest.kind == "production_readiness").order_by(ApprovalRequest.id)).all()
    return [_out(r) for r in rows]


@router.post("/readiness-reviews")
def open_readiness(project_id: int, body: ReadinessOpen, request: Request, session: Session = Depends(get_session)):
    _project(session, project_id)
    me = rbac.acting_as(request, body.role)
    review = _guard(lambda: readiness.open_review(session, request.app.state.graph, project_id, _m(body.release),
                                                  me.username, body.role))
    session.commit()
    return _out(review)


@router.post("/readiness-reviews/{review_id}/decision")
def decide_readiness(project_id: int, review_id: int, body: ReadinessDecision, request: Request,
                     session: Session = Depends(get_session)):
    review = _request(session, project_id, review_id, "production_readiness")
    me = rbac.acting_as(request, body.reviewer_role)
    _guard(lambda: readiness.decide(session, request.app.state.graph, review, me.username, body.reviewer_role,
                                    body.decision, _m(body.comment) or "", body.attest,
                                    {k: _m(v) or "" for k, v in body.waivers.items()}))
    session.commit()
    return _out(review)
