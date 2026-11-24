"""Coordinator agent: controls the workflow, distributes work to agents and owns every routing decision.

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


# ---------- Routing decisions ----------

def after_validation(state: ProjectState) -> str:
    blocking = [q for q in state.get("clarifications", []) if q["severity"] == "blocking"]
    if blocking and state.get("clarification_round", 0) < get_settings().max_clarification_rounds:
        return "clarification_gate"
    return "baseline_approval"


def after_clarification(state: ProjectState) -> str:
    # New answers were stored as sources → re-run extraction; otherwise proceed to approval.
    return "intake" if state.get("clarified") else "baseline_approval"


def after_baseline(state: ProjectState) -> str:
    approvals = state.get("baseline_approvals", [])
    if approvals and approvals[-1].get("decision") == "regenerate":
        return "intake"
    from app.agents.approval import pending_baseline_approvers
    return "persist_baseline" if not pending_baseline_approvers(state) else "baseline_approval"


def after_sdlc(state: ProjectState) -> str:
    approvals = state.get("sdlc_approvals", [])
    if approvals and approvals[-1].get("decision") == "regenerate":
        return "sdlc_selection"
    from app.agents.approval import pending_sdlc_approvers
    return "sdlc_workflow" if not pending_sdlc_approvers(state) else "sdlc_approval"


def after_workflow(state: ProjectState) -> str:
    approvals = state.get("workflow_approvals", [])
    if approvals and approvals[-1].get("decision") == "regenerate":
        return "sdlc_workflow"
    from app.agents.approval import pending_workflow_approvers
    return "documentation" if not pending_workflow_approvers(state) else "workflow_approval"
