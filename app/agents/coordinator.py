"""Coordinator agent: controls the workflow, distributes work, scores the results and runs the human gates.

It never calls the language model. Its graph nodes:
  intake             load the masked sources, start a pass, fan out one extraction per source chunk
  consolidate        merge the chunk results and attach traceability to the source
  assess             combine the review and compliance & security findings, run the deterministic quality checks,
                     score the run and finalise the stakeholder questions
  requirements_gate  "Approve requirements": answer blocking questions (if any), then sign off the baseline
  plan_gate          "Approve plan": approve the SDLC model, then the project workflow
Routing is deterministic (rules over shared state), never delegated to an LLM, so runs are reproducible.
"""

from langgraph.types import Send
from sqlalchemy import select

from app.audit import record
from app.catalog.loader import get_catalog
from app.config import get_settings
from app.db import SessionLocal
from app.graph.state import ProjectState
from app.models import Source

CHUNK_CHARS = 8000


def chunk_text(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Split on paragraph boundaries into chunks of at most ~size characters."""
    chunks, current = [], ""
    for para in text.split("\n\n"):
        if current and len(current) + len(para) > size:
            chunks.append(current)
            current = ""
        current = f"{current}\n\n{para}" if current else para
        while len(current) > size:  # single oversized paragraph
            chunks.append(current[:size])
            current = current[size:]
    if current.strip():
        chunks.append(current)
    return chunks


def intake(state: ProjectState) -> ProjectState:
    """Load the project's masked sources and reset per-pass results."""
    with SessionLocal() as session:
        rows = session.scalars(select(Source).where(Source.project_id == state["project_id"]).order_by(Source.id)).all()
        sources = [{"id": s.id, "title": s.title, "source_type": s.source_type, "stakeholder_role": s.stakeholder_role,
                    "sensitivity": s.sensitivity, "injection_flags": s.injection_flags, "text": s.masked_text}
                   for s in rows]
    iteration = state.get("iteration", 0) + 1
    chunks = sum(len(chunk_text(s["text"])) for s in sources)
    record(state["project_id"], "coordinator_agent", "pass_started",
           {"iteration": iteration, "sources": len(sources), "chunks": chunks,
            "clarification_round": state.get("clarification_round", 0)})
    from app.security.provenance import snapshot
    provenance = snapshot()  # step 17: which model, prompts, rules and knowledge produced this pass
    record(state["project_id"], "coordinator_agent", "provenance_recorded", provenance)
    return {"sources": sources, "extractions": None, "iteration": iteration, "provenance": provenance,
            "baseline_approvals": [], "sdlc_approvals": []}


def dispatch_extraction(state: ProjectState) -> list[Send]:
    """Fan out one extraction task per source chunk (runs in parallel)."""
    return [
        Send("extraction", {"project_id": state["project_id"], "domain": state["domain"],
                            "source": {k: v for k, v in src.items() if k != "text"},
                            "text": chunk, "chunk": i, "feedback": state.get("feedback", "")})
        for src in state["sources"]
        for i, chunk in enumerate(chunk_text(src["text"]))
    ]


def consolidate(state: ProjectState) -> ProjectState:
    """Merge per-chunk results, assign stable IDs (FR-LOAN-001) and attach traceability to the source."""
    domain = get_catalog().domain(state["domain"])
    code = domain.code if domain else "GEN"
    counters = {"functional": 0, "non_functional": 0}
    requirements = []
    for ex in state.get("extractions", []):
        src = ex["source"]
        for r in ex["requirements"]:
            counters[r["type"]] += 1
            prefix = "FR" if r["type"] == "functional" else "NFR"
            requirements.append(r | {
                "id": f"{prefix}-{code}-{counters[r['type']]:03d}",
                "origin": "extracted", "status": "proposed",
                "source_id": src["id"], "source_title": src["title"],
                "source_type": src["source_type"], "stakeholder_role": src["stakeholder_role"],
            })
    record(state["project_id"], "coordinator_agent", "consolidated", {"requirements": len(requirements)})
    return {"requirements": requirements}


# ---------- Scoring ----------

def assess(state: ProjectState) -> ProjectState:
    """Deterministic join of the two analysis agents: quality checks, scores and the final question list."""
    from app.agents.clarification import finalise_questions, question_issues
    from app.agents.validation import validation

    out = validation(state)
    questions = finalise_questions(state.get("clarifications", []), out["returned"])
    record(state["project_id"], "coordinator_agent", "questions_finalised",
           {"total": len(questions), "blocking": sum(q["severity"] == "blocking" for q in questions),
            "added_for_failed_checks": sum(q["origin"] == "validation" for q in questions)})
    return out | {"clarifications": questions, "issues": out["issues"] + question_issues(questions)}


# ---------- Routing decisions ----------

def after_requirements(state: ProjectState) -> str:
    if state.get("gate_step") == "questions":
        # New answers were stored as sources → analyse again; otherwise go on to sign-off.
        return "intake" if state.get("clarified") else "requirements_gate"
    approvals = state.get("baseline_approvals", [])
    if approvals and approvals[-1].get("decision") == "regenerate":
        return "intake"
    from app.agents.approval import pending_baseline_approvers
    return "freeze_baseline" if not pending_baseline_approvers(state) else "requirements_gate"


def after_plan(state: ProjectState) -> str:
    from app.agents.approval import pending_sdlc_approvers, pending_workflow_approvers
    sdlc_approvals = state.get("sdlc_approvals", [])
    if sdlc_approvals and sdlc_approvals[-1].get("decision") == "regenerate":
        return "planning"
    if pending_sdlc_approvers(state):
        return "plan_gate"
    if state.get("sdlc_workflow", {}).get("model") != state.get("sdlc_decision", {}).get("model"):
        return "planning"  # approvers chose another model: rebuild the workflow for it
    workflow_approvals = state.get("workflow_approvals", [])
    if workflow_approvals and workflow_approvals[-1].get("decision") == "regenerate":
        return "planning"
    return "documentation" if not pending_workflow_approvers(state) else "plan_gate"
