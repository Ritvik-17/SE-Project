"""Deploy, monitor and improve (step 20): staged deployment, analyst comparison, quality monitoring, domain expansion,
usage and the per-project accountability pack."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ops
from app.audit import record
from app.catalog.loader import get_catalog
from app.db import get_session
from app.models import Artifact, Feedback, LlmCall, Project, RetrievalLog
from app.security import rbac

router = APIRouter(tags=["deploy-monitor-improve"])


def _project(session: Session, project_id: int) -> Project:
    p = session.get(Project, project_id)
    if p is None:
        raise HTTPException(404, "Project not found")
    return p


# ---------- Per project ----------

@router.get("/projects/{project_id}/usage")
def project_usage(project_id: int):
    return ops.usage(project_id)


@router.get("/projects/{project_id}/llm-calls")
def llm_calls(project_id: int, include_text: bool = False, session: Session = Depends(get_session)):
    """Every prompt sent to the model for this project (decrypted text only on request)."""
    rows = session.scalars(select(LlmCall).where(LlmCall.project_ref == project_id).order_by(LlmCall.id)).all()
    return [{"id": c.id, "at": c.created_at.isoformat(), "agent": c.agent, "purpose": c.purpose, "model": c.model,
             "schema": c.schema, "prompt_sha256": c.prompt_sha256, "input_tokens": c.input_tokens,
             "cached_tokens": c.cached_tokens, "output_tokens": c.output_tokens, "cost_usd": c.cost_usd,
             "latency_ms": c.latency_ms, "filtered": c.filtered}
            | ({"prompt": c.prompt, "response": c.response} if include_text else {}) for c in rows]


@router.get("/projects/{project_id}/retrievals")
def retrievals(project_id: int, session: Session = Depends(get_session)):
    rows = session.scalars(select(RetrievalLog).where(RetrievalLog.project_ref == project_id).order_by(RetrievalLog.id)).all()
    return [{"id": r.id, "at": r.created_at.isoformat(), "agent": r.agent, "queries": r.queries, "filters": r.filters,
             "hits": r.hits} for r in rows]


@router.get("/projects/{project_id}/artifacts/history")
def artifact_history(project_id: int, session: Session = Depends(get_session)):
    rows = session.scalars(select(Artifact).where(Artifact.project_id == project_id)
                           .order_by(Artifact.version.desc(), Artifact.kind)).all()
    versions: dict[int, dict] = {}
    for a in rows:
        v = versions.setdefault(a.version, {"version": a.version, "status": a.status, "created_at": a.created_at.isoformat(),
                                            "superseded_at": a.superseded_at.isoformat() if a.superseded_at else None,
                                            "kinds": []})
        v["kinds"].append(a.kind)
    return list(versions.values())


@router.get("/projects/{project_id}/accountability-pack")
def accountability_pack(project_id: int, request: Request, session: Session = Depends(get_session)):
    _project(session, project_id)
    me = rbac.principal(request)
    record(project_id, me.username, "accountability_pack_exported", {})
    return ops.accountability_pack(request.app.state.graph, project_id)


class AnalystComparison(BaseModel):
    requirements: list[str] = Field(min_length=1, description="The business analyst's own requirement list")
    threshold: float = Field(0.80, ge=0.5, le=0.99)


@router.post("/projects/{project_id}/analyst-comparison")
def analyst_comparison(project_id: int, body: AnalystComparison, request: Request, session: Session = Depends(get_session)):
    _project(session, project_id)
    try:
        return ops.compare_with_analyst(request.app.state.graph, project_id, rbac.principal(request).username,
                                        body.requirements, body.threshold)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


class FeedbackIn(BaseModel):
    role: str
    sus: list[int] = Field(min_length=10, max_length=10, description="System Usability Scale answers, 1-5 each")
    usefulness: int = Field(ge=1, le=5)
    trust: int = Field(ge=1, le=5)
    comment: str = ""


@router.post("/projects/{project_id}/feedback")
def submit_feedback(project_id: int, body: FeedbackIn, request: Request, session: Session = Depends(get_session)):
    _project(session, project_id)
    me = rbac.acting_as(request, body.role)
    if any(not 1 <= x <= 5 for x in body.sus):
        raise HTTPException(422, "SUS answers must be between 1 and 5")
    row = session.scalar(select(Feedback).where(Feedback.project_id == project_id, Feedback.user_id == me.id))
    if row is None:
        row = Feedback(project_id=project_id, user_id=me.id)
        session.add(row)
    row.role, row.sus, row.usefulness, row.trust, row.comment = body.role, body.sus, body.usefulness, body.trust, body.comment
    session.commit()
    from eval.metrics import sus_score
    record(project_id, me.username, "feedback", {"role": body.role, "sus": sus_score(body.sus),
                                                 "usefulness": body.usefulness, "trust": body.trust})
    return {"sus_score": sus_score(body.sus)}


@router.get("/projects/{project_id}/feedback")
def list_feedback(project_id: int, session: Session = Depends(get_session)):
    from eval.metrics import sus_score
    rows = session.scalars(select(Feedback).where(Feedback.project_id == project_id)).all()
    return [{"role": f.role, "sus_score": sus_score(f.sus), "usefulness": f.usefulness, "trust": f.trust,
             "comment": f.comment, "at": f.created_at.isoformat()} for f in rows]


# ---------- System ----------

class DeploymentIn(BaseModel):
    stage: Literal["advisory", "assisted"]
    require_current_evaluation: bool = True
    reason: str = Field(min_length=10)


@router.get("/admin/deployment")
def get_deployment():
    dep = ops.get_setting("deployment", ops.DEFAULT_DEPLOYMENT)
    return dep | {"evaluation": ops.evaluation_status()}


@router.post("/admin/deployment")
def set_deployment(body: DeploymentIn, request: Request):
    me = rbac.principal(request)
    if body.stage == "assisted" and body.require_current_evaluation and not ops.evaluation_status()["current_evaluation_passed"]:
        raise HTTPException(409, "Run and pass an evaluation for the current configuration before leaving advisory mode")
    value = {"stage": body.stage, "require_current_evaluation": body.require_current_evaluation, "reason": body.reason}
    ops.set_setting("deployment", value, me.username)
    record(None, me.username, "deployment_stage_changed", value)
    return get_deployment()


@router.get("/admin/evaluation-status")
def evaluation_status(domain: str | None = None):
    return ops.evaluation_status(domain)


@router.get("/admin/quality")
def quality():
    return ops.quality_monitor()


@router.get("/admin/usage")
def usage():
    return ops.usage()


@router.get("/admin/domains")
def domains():
    return [ops.domain_readiness(d.id) | {"name": d.name} for d in get_catalog().domains]


class DomainIn(BaseModel):
    active: bool
    justification: str = ""


@router.post("/admin/domains/{domain_id}")
def set_domain(domain_id: str, body: DomainIn, request: Request):
    try:
        return ops.set_domain(domain_id, body.active, rbac.principal(request).username, body.justification)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
