from contextlib import asynccontextmanager
from typing import Annotated
from uuid import uuid4

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.concurrency import run_in_threadpool
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import llm
from app.audit import record
from app.agents.interview_policy import coverage_summary
from app.catalog.loader import get_catalog, interview_plan, interview_template
from app.config import get_settings
from app.db import get_session, init_db
from app.graph.builder import build_analysis_graph, build_interview_graph
from app.ingestion.parsers import UnsupportedFileError, extract_text
from app.ingestion.service import IngestionError, ingest, questionnaire_to_text
from app.llm import LLMNotConfiguredError
from app.api.auth_routes import router as auth_router
from app.api.hitl_routes import router as hitl_router
from app.api.kb_routes import router as kb_router
from app.api.ops_routes import router as ops_router
from app.kb.collections import JURISDICTIONS
from app.kb.ingest import KbError
from app.models import Artifact, AuditLog, Project, ProjectMember, Requirement, Source
from app.schemas import (BaselineDecision, ClarificationResponse, InterviewReply, InterviewStart, InterviewSubmission,
                         ProjectCreate, ProjectOut, RunStatus, SdlcDecision, SourceOut, WorkflowDecision)
from app.audit import current_principal
from app.security import monitoring, provenance, rbac, retention
from app.security.crypto import checkpoint_serializer, keyring
from app.security.masking import mask

GateDecision = Annotated[ClarificationResponse | BaselineDecision | SdlcDecision | WorkflowDecision,
                         Field(discriminator="gate")]


@asynccontextmanager
async def lifespan(app: FastAPI):
    keyring()  # step 17: refuse to start without an encryption key (data at rest is encrypted)
    provenance.check_model_pinning()
    init_db()
    pool = ConnectionPool(
        get_settings().checkpoint_db_url,
        max_size=10,
        open=True,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    checkpointer = PostgresSaver(pool, serde=checkpoint_serializer())  # checkpoints encrypted at rest
    checkpointer.setup()
    app.state.graph = build_analysis_graph(checkpointer)
    app.state.interview_graph = build_interview_graph(checkpointer)
    yield
    pool.close()


app = FastAPI(title="Financial Requirements Engineering Agent", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(kb_router)
app.include_router(hitl_router)
app.include_router(ops_router)

SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                    "Cache-Control": "no-store", "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'"}


@app.middleware("http")
async def security(request: Request, call_next):
    """Step 17: authentication and RBAC on every request, security headers, request metrics."""
    import time
    started = time.perf_counter()
    try:
        principal = await run_in_threadpool(rbac.authorize, request)
    except HTTPException as exc:
        response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        principal = None
    else:
        if principal is not None:
            request.state.principal = principal
            current_principal.set(principal.username)  # flows into the endpoint and the agents it runs
        response = await call_next(request)
    docs = request.url.path in ("/docs", "/redoc")
    for k, v in SECURITY_HEADERS.items():
        if not (docs and k == "Content-Security-Policy"):
            response.headers.setdefault(k, v)
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = f"max-age={get_settings().hsts_max_age}; includeSubDomains"
    route = monitoring.route_of(request.url.path)
    monitoring.inc("http_requests_total", route=route, method=request.method, status=f"{response.status_code // 100}xx")
    monitoring.inc("http_request_seconds_sum", time.perf_counter() - started, route=route)
    return response


app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(LLMNotConfiguredError)
def llm_not_configured(_: Request, exc: LLMNotConfiguredError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(IngestionError)
@app.exception_handler(KbError)
@app.exception_handler(UnsupportedFileError)
def bad_input(_: Request, exc: ValueError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


# ---------- Helpers ----------

def _config(project_id: int) -> dict:
    # "-v2": threads created by the earlier single-agent graph are not resumed by this graph.
    return {"configurable": {"thread_id": f"project-{project_id}-v2"}}


def _interview_config(session_id: str) -> dict:
    return {"configurable": {"thread_id": f"interview-{session_id}"}}


def _masked(value: str) -> str:
    """Free text from people, before it enters the graph: personal data masked, instruction-like text removed."""
    if not value or not value.strip():
        return value
    from app.security.filters import neutralise
    safe, removed = neutralise(mask(value).text)
    if removed:
        record(None, "api", "injection_neutralised", {"phrases": removed})
    return safe


def _run_status(request: Request, project_id: int) -> RunStatus:
    snapshot = request.app.state.graph.get_state(_config(project_id))
    interrupts = [i.value for task in snapshot.tasks for i in task.interrupts]
    if not snapshot.values:
        status = "not_started"
    elif interrupts:
        status = "awaiting_input"
    elif snapshot.next:
        status = "running"
    else:
        status = "completed"
    # Keep the payload lean: raw chunk results and source text are available elsewhere.
    values = {k: v for k, v in snapshot.values.items() if k != "extractions"}
    if "sources" in values:
        values["sources"] = [{k: v for k, v in s.items() if k != "text"} for s in values["sources"]]
    pending = interrupts[0] if interrupts else None
    return RunStatus(project_id=project_id, status=status, gate=pending["gate"] if pending else None,
                     next=list(snapshot.next), pending=pending, state=values)


def _get_project(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


def _source_out(s: Source, with_text: bool = False) -> SourceOut:
    return SourceOut.model_validate({c: getattr(s, c) for c in SourceOut.model_fields if c != "masked_text"}
                                    | {"masked_text": s.masked_text if with_text else None})


def _interview_status(request: Request, project_id: int, session_id: str) -> dict:
    snap = request.app.state.interview_graph.get_state(_interview_config(session_id))
    if not snap.values or snap.values.get("project_id") != project_id:
        raise HTTPException(404, "Interview session not found")
    interrupts = [i.value for task in snap.tasks for i in task.interrupts]
    v = snap.values
    plan = interview_plan(v["role"], v["domain"])
    coverage = v.get("coverage", {})
    topics = [{"id": t["id"], "name": t["name"], "priority": t["priority"],
               "slots": [{**s, "answered": s["id"] in coverage.get(t["id"], {}).get("answered", []),
                          "in_passing": s["id"] in coverage.get(t["id"], {}).get("in_passing", [])} for s in t["slots"]],
               "status": coverage.get(t["id"], {}).get("status", "pending"),
               "follow_ups": coverage.get(t["id"], {}).get("follow_ups", 0)} for t in plan]
    return {"session_id": session_id, "role": v["role"],
            "status": "awaiting_answer" if interrupts else "completed",
            "question": interrupts[0] if interrupts else None,
            "transcript": v.get("transcript", []), "topics": topics,
            "summary": coverage_summary(plan, coverage) if coverage else None,
            "open_questions": [q for q in v.get("open_questions", [])
                               if q["slot"] not in coverage.get(q["topic"], {}).get("answered", [])],
            "contradictions": v.get("contradictions", []), "source_id": v.get("source_id")}


# ---------- Health, catalog, graph ----------

@app.get("/health")
def health(session: Session = Depends(get_session)):
    session.execute(text("SELECT 1"))
    return {"status": "ok", "db": "ok", "model": get_settings().openai_model,
            "llm_configured": bool(get_settings().openai_api_key)}


@app.get("/catalog")
def catalog():
    """System scope: requirement categories, stakeholder roles, domains, input sources and outputs."""
    from app import ops
    data = get_catalog().model_dump(exclude={"roles": {"__all__": {"interview"}}})
    for d in data["domains"]:  # step 20: domains activated or withdrawn by administrators
        d["status"] = ops.domain_status(d["id"])
    return data


@app.get("/catalog/roles/{role_id}/interview")
def get_interview_template(role_id: str, domain: str | None = None):
    try:
        return interview_template(role_id, domain)
    except KeyError:
        raise HTTPException(404, f"Unknown role '{role_id}'")


@app.get("/catalog/roles/{role_id}/interview-plan")
def get_interview_plan(role_id: str, domain: str | None = None):
    """The adaptive interview's topics for a role: priority, checklist points and suggested questions."""
    try:
        return interview_plan(role_id, domain)
    except KeyError:
        raise HTTPException(404, f"Unknown role '{role_id}'")


@app.get("/graph")
def graph(request: Request):
    """Mermaid diagrams of the agent graphs, generated from the compiled LangGraph objects."""
    return {"analysis": request.app.state.graph.get_graph().draw_mermaid(),
            "interview": request.app.state.interview_graph.get_graph().draw_mermaid()}


# ---------- Projects ----------

@app.post("/projects", response_model=ProjectOut)
def create_project(body: ProjectCreate, request: Request, session: Session = Depends(get_session)):
    domain = get_catalog().domain(body.domain)
    if domain is None:
        raise HTTPException(422, f"Unknown domain '{body.domain}'")
    from app import ops
    if ops.domain_status(domain.id) != "active":
        raise HTTPException(422, f"'{domain.name}' is planned but not yet enabled")
    if body.jurisdiction not in JURISDICTIONS:
        raise HTTPException(422, f"Unknown jurisdiction '{body.jurisdiction}'")
    me = rbac.principal(request)
    stage, why = ops.stage_for_new_project(body.domain)  # step 20: advisory until evaluated
    project = Project(name=body.name, domain=body.domain, jurisdiction=body.jurisdiction, created_by=me.id,
                      deployment_stage=stage)
    session.add(project)
    session.flush()
    session.add(ProjectMember(project_id=project.id, user_id=me.id, added_by=me.username))
    session.commit()
    record(project.id, "api", "project_created", body.model_dump() | {"deployment_stage": stage, "advisory_reason": why})
    return ProjectOut(id=project.id, name=project.name, domain=project.domain, status=project.status,
                      jurisdiction=project.jurisdiction, deployment_stage=stage)


@app.get("/projects", response_model=list[ProjectOut])
def list_projects(request: Request, session: Session = Depends(get_session)):
    me = rbac.principal(request)
    q = select(Project).order_by(Project.id.desc())
    if not me.is_admin:  # session isolation: only projects the user is a member of
        q = q.where(Project.id.in_(select(ProjectMember.project_id).where(ProjectMember.user_id == me.id)))
    projects = session.scalars(q).all()
    return [ProjectOut(id=p.id, name=p.name, domain=p.domain, status=p.status, jurisdiction=p.jurisdiction,
                       deployment_stage=p.deployment_stage)
            for p in projects]


@app.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, session: Session = Depends(get_session)):
    p = _get_project(session, project_id)
    return ProjectOut(id=p.id, name=p.name, domain=p.domain, status=p.status, jurisdiction=p.jurisdiction,
                       deployment_stage=p.deployment_stage)


# ---------- Input sources ----------

@app.post("/projects/{project_id}/sources", response_model=SourceOut)
async def add_source(project_id: int, source_type: str = Form(...), title: str = Form(...),
                     stakeholder_role: str | None = Form(None), content: str | None = Form(None),
                     file: UploadFile | None = File(None), session: Session = Depends(get_session)):
    """Add a source as pasted text or an uploaded file. It is parsed, masked and classified before storage."""
    _get_project(session, project_id)
    if file is not None and file.filename:
        raw = extract_text(file.filename, await file.read())
        filename = file.filename
    elif content:
        raw, filename = content, None
    else:
        raise HTTPException(422, "Provide either 'content' or 'file'")
    return _source_out(ingest(project_id, source_type, title, raw, stakeholder_role or None, filename))


@app.post("/projects/{project_id}/interviews", response_model=SourceOut)
def submit_interview(project_id: int, body: InterviewSubmission, session: Session = Depends(get_session)):
    """Store answers to a role-specific interview template as a structured questionnaire source."""
    _get_project(session, project_id)
    role = get_catalog().role(body.stakeholder_role)
    if role is None:
        raise HTTPException(422, f"Unknown role '{body.stakeholder_role}'")
    answers = [a.model_dump() for a in body.answers]
    if not any(a["answer"].strip() for a in answers):
        raise HTTPException(422, "At least one question must be answered")
    return _source_out(ingest(project_id, "questionnaire", body.title or f"{role.name} interview",
                              questionnaire_to_text(role.name, answers), body.stakeholder_role))


@app.get("/projects/{project_id}/sources", response_model=list[SourceOut])
def list_sources(project_id: int, session: Session = Depends(get_session)):
    rows = session.scalars(select(Source).where(Source.project_id == project_id).order_by(Source.id)).all()
    return [_source_out(s) for s in rows]


@app.get("/projects/{project_id}/sources/{source_id}", response_model=SourceOut)
def get_source(project_id: int, source_id: int, session: Session = Depends(get_session)):
    s = session.get(Source, source_id)
    if not s or s.project_id != project_id:
        raise HTTPException(404, "Source not found")
    return _source_out(s, with_text=True)


@app.delete("/projects/{project_id}/sources/{source_id}", status_code=204)
def delete_source(project_id: int, source_id: int, session: Session = Depends(get_session)):
    s = session.get(Source, source_id)
    if not s or s.project_id != project_id:
        raise HTTPException(404, "Source not found")
    session.delete(s)
    session.commit()
    record(project_id, "api", "source_deleted", {"source_id": source_id})


# ---------- Adaptive interviews (stakeholder-interaction agent) ----------

@app.post("/projects/{project_id}/interview-sessions")
def start_interview(project_id: int, body: InterviewStart, request: Request, session: Session = Depends(get_session)):
    project = _get_project(session, project_id)
    if get_catalog().role(body.stakeholder_role) is None:
        raise HTTPException(422, f"Unknown role '{body.stakeholder_role}'")
    llm.get_model()  # fail fast before creating a session
    session_id = uuid4().hex
    request.app.state.interview_graph.invoke(
        {"project_id": project_id, "domain": project.domain, "role": body.stakeholder_role, "transcript": []},
        _interview_config(session_id))
    record(project_id, "stakeholder_interaction_agent", "interview_started",
           {"session_id": session_id, "role": body.stakeholder_role})
    return _interview_status(request, project_id, session_id)


@app.post("/projects/{project_id}/interview-sessions/{session_id}/reply")
def reply_interview(project_id: int, session_id: str, body: InterviewReply, request: Request):
    if _interview_status(request, project_id, session_id)["status"] != "awaiting_answer":
        raise HTTPException(409, "Interview already completed")
    request.app.state.interview_graph.invoke(
        Command(resume={"answer": _masked(body.answer), "finish": body.finish}), _interview_config(session_id))
    return _interview_status(request, project_id, session_id)


@app.get("/projects/{project_id}/interview-sessions/{session_id}")
def get_interview(project_id: int, session_id: str, request: Request):
    return _interview_status(request, project_id, session_id)


# ---------- Requirements-analysis workflow ----------

@app.post("/projects/{project_id}/runs", response_model=RunStatus)
def start_run(project_id: int, request: Request, session: Session = Depends(get_session)):
    """Run the multi-agent analysis over all sources; returns at the first human gate."""
    project = _get_project(session, project_id)
    if not session.scalar(select(func.count()).select_from(Source).where(Source.project_id == project_id)):
        raise HTTPException(422, "Add at least one input source before running the analysis")
    llm.get_model()  # fail fast (503) before any state changes when the LLM is not configured
    project.status = "analysing"
    session.commit()
    try:
        request.app.state.graph.invoke({"project_id": project_id, "domain": project.domain,
                                        "jurisdiction": project.jurisdiction, "iteration": 0,
                                        "clarification_round": 0, "feedback": ""}, _config(project_id))
    except Exception:
        project.status = "failed"  # visible in the UI; starting a new run retries from the beginning
        session.commit()
        raise
    return _run_status(request, project_id)


@app.post("/projects/{project_id}/decision", response_model=RunStatus)
def submit_decision(project_id: int, request: Request, body: GateDecision = Body(...),
                    session: Session = Depends(get_session)):
    """Answer the pending human gate (clarification, baseline, SDLC or workflow approval) and resume the graph.

    Human-in-the-loop rules (step 16) are enforced here, before the graph resumes; see guide/human_in_the_loop.md."""
    _get_project(session, project_id)
    run = _run_status(request, project_id)
    if run.status != "awaiting_input":
        raise HTTPException(409, "No decision is pending for this project")
    if body.gate != run.gate:
        raise HTTPException(409, f"Pending gate is '{run.gate}', not '{body.gate}'")
    pending = run.pending

    me = rbac.principal(request)
    if isinstance(body, ClarificationResponse):
        body.responder = me.username
        for a in body.answers:
            a.answer = _masked(a.answer)
        body.feedback = _masked(body.feedback)
        if body.decision == "regenerate" and not body.feedback.strip():
            raise HTTPException(422, "Feedback is required to regenerate")
    else:
        if get_catalog().role(body.reviewer_role) is None:
            raise HTTPException(422, f"Unknown role '{body.reviewer_role}'")
        rbac.acting_as(request, body.reviewer_role)  # 403 unless the account holds this role
        body.reviewer = me.username
        allowed = pending["pending_approvers"] if body.decision == "approve" else pending["required_approvers"]
        if body.reviewer_role not in allowed:
            raise HTTPException(403, f"Role '{body.reviewer_role}' cannot {body.decision} here; expected one of {allowed}")
        body.feedback = _masked(body.feedback)
        if isinstance(body, BaselineDecision):
            ids = {r["id"] for r in pending["requirements"]}
            if unknown := [e.id for e in body.edits if e.id not in ids]:
                raise HTTPException(422, f"Unknown requirement IDs: {unknown}")
            for e in body.edits:
                e.statement = _masked(e.statement) if e.statement else e.statement
                if e.action == "modify" and not (e.statement or "").strip():
                    raise HTTPException(422, f"Modifying {e.id} needs the new statement")
            from app.hitl.controls import undecided
            items = pending.get("decision_items", {})
            role = body.reviewer_role
            if foreign := [e.id for e in body.edits if e.id in items and items[e.id]["owner"] != role]:
                owners = ", ".join(f"{i} → {get_catalog().role(items[i]['owner']).name}" for i in foreign)
                raise HTTPException(422, f"These requirements must be decided by their owning role: {owners}")
            if body.decision == "approve" and (open_ := undecided(items, role, [e.model_dump() for e in body.edits])):
                raise HTTPException(422, f"Requirements needing your decision as {get_catalog().role(role).name} "
                                         f"(accept, modify or reject): {', '.join(open_)}")
            interps = {m["id"]: m for m in pending.get("interpretations", [])}
            if body.interpretations and role != "compliance_legal":
                raise HTTPException(422, "Only compliance & legal decides regulatory interpretations")
            if bad := [d.id for d in body.interpretations if d.id not in interps]:
                raise HTTPException(422, f"Unknown or not-for-review interpretations: {bad}")
            for d in body.interpretations:
                if d.action == "modify" and not ((d.regulation or "").strip() or (d.obligation or "").strip()):
                    raise HTTPException(422, f"Modifying {d.id} needs the corrected regulation or obligation")
                d.regulation, d.obligation, d.note = _masked(d.regulation or ""), _masked(d.obligation or ""), _masked(d.note)
            if body.decision == "approve" and role == "compliance_legal":
                given = {d.id for d in body.interpretations}
                if open_ := [i for i, m in interps.items() if not m.get("legal_decision") and i not in given]:
                    raise HTTPException(422, f"Regulatory interpretations need your accept, reject or modify decision: "
                                             f"{', '.join(open_)}")
        elif isinstance(body, WorkflowDecision):
            names = {p["name"] for p in pending["workflow"]["phases"]}
            if bad := [e.phase for e in body.edits if e.phase not in names]:
                raise HTTPException(422, f"Unknown workflow phases: {bad}")
            for e in body.edits:
                if e.field == "duration_weeks" and not isinstance(e.value, (int, float)):
                    raise HTTPException(422, "duration_weeks must be a number")
                e.value = [_masked(v) for v in e.value] if isinstance(e.value, list) else \
                    (_masked(e.value) if isinstance(e.value, str) else e.value)
            if bad := [k for k in body.schedule if k not in ("iterations", "iteration_length_weeks", "iterations_per_release", "cycles")]:
                raise HTTPException(422, f"Unknown schedule settings: {bad}")
        else:
            if body.selected_model and body.selected_model not in {r["model"] for r in pending["recommendations"]}:
                raise HTTPException(422, f"Unknown SDLC model '{body.selected_model}'")
            known = {c["id"] for c in pending.get("characteristics", [])}
            if unknown_q := [q for q in body.characteristic_answers if q not in known]:
                raise HTTPException(422, f"Unknown SDLC-selection questions: {unknown_q}")
            top = pending["recommendations"][0]["model"]
            if body.decision == "approve" and body.selected_model and body.selected_model != top and not body.feedback.strip():
                raise HTTPException(422, f"Give a justification for choosing {body.selected_model} instead of the "
                                         f"recommended {top}")
            if body.decision == "regenerate" and body.characteristic_answers and not body.feedback.strip():
                body.feedback = "Re-rank with updated project characteristics: " + ", ".join(
                    f"{k}={v}" for k, v in body.characteristic_answers.items())
        if body.decision == "regenerate" and not body.feedback.strip():
            raise HTTPException(422, "Feedback is required to regenerate")

    request.app.state.graph.invoke(Command(resume=body.model_dump()), _config(project_id))
    return _run_status(request, project_id)


@app.post("/projects/{project_id}/archive")
def archive_project(project_id: int, request: Request, session: Session = Depends(get_session)):
    """Start the retention clock: archived projects are purged after RETENTION_PROJECT_AFTER_ARCHIVE_DAYS."""
    from datetime import datetime, timezone
    project = _get_project(session, project_id)
    project.archived_at = datetime.now(timezone.utc)
    session.commit()
    record(project_id, "api", "project_archived", {"legal_hold": project.legal_hold})
    return {"project_id": project_id, "archived_at": project.archived_at.isoformat(), "legal_hold": project.legal_hold}


@app.get("/admin/retention")
def retention_plan():
    return retention.plan()


@app.post("/admin/retention/apply")
def retention_apply(request: Request):
    return retention.apply(rbac.principal(request).username)


@app.get("/admin/provenance")
def current_provenance():
    return provenance.snapshot()


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    return monitoring.render()


@app.get("/projects/{project_id}/run", response_model=RunStatus)
def get_run(project_id: int, request: Request, session: Session = Depends(get_session)):
    _get_project(session, project_id)
    return _run_status(request, project_id)


@app.get("/projects/{project_id}/requirements")
def get_requirements(project_id: int, session: Session = Depends(get_session)):
    rows = session.scalars(select(Requirement).where(Requirement.project_id == project_id)).all()
    # Step 8 standard structure (see app/agents/standards.py REQUIREMENT_FIELDS)
    return [{"req_id": r.req_id, "statement": r.statement, "type": r.req_type, "categories": r.categories,
             "source_stakeholder": r.stakeholder_role or r.origin, "business_justification": r.business_justification,
             "priority": r.priority, "dependencies": r.dependencies, "assumptions": r.assumptions,
             "acceptance_criteria": r.acceptance_criteria, "applicable_regulations": r.applicable_regulations,
             "risk_level": r.risk_level, "confidence": r.confidence, "approval_status": r.approval_status,
             "origin": r.origin, "source_id": r.source_id, "source_quote": r.source_quote,
             "grounding_support": r.grounding_support, "citations": r.citations,
             "stakeholder_role": r.stakeholder_role, "source_type": r.source_type} for r in rows]


@app.get("/projects/{project_id}/artifacts")
def get_artifacts(project_id: int, session: Session = Depends(get_session)):
    rows = session.scalars(select(Artifact).where(Artifact.project_id == project_id,
                                                  Artifact.superseded_at.is_(None))).all()  # current version
    return {a.kind: a.content["data"] for a in rows}


@app.get("/projects/{project_id}/audit")
def get_audit(project_id: int, session: Session = Depends(get_session)):
    rows = session.scalars(select(AuditLog).where(AuditLog.project_id == project_id).order_by(AuditLog.id)).all()
    return [{"at": r.created_at.isoformat(), "actor": r.actor, "action": r.action, "detail": r.detail} for r in rows]
