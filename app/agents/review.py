"""Review agent: is each requirement good, consistent and safe, and what must stakeholders still answer?

One agent with four steps (each a guarded step with its own permissions, see app/security/agent_permissions.py):
  quality_review      ambiguity, incompleteness, infeasibility, lack of testability (step 10)   ┐
  conflict_detection  contradictions, duplicates and overlaps between requirements/stakeholders  ├ in parallel
  risk_analysis       risk register: likelihood × impact, mitigation, linked requirements        ┘
  clarification       a question for each problem found, routed to the role best placed to answer

The questions are drafted here from the agent's own findings. Problems found by the compliance & security agent
(missing controls, contradicted policies) are added by the coordinator when it scores the run: every requirement
that still fails a check gets a deterministic fallback question (clarification.finalise_questions).
"""

from app.agents import clarification, conflict, quality_review, risk
from app.agents.common import run_steps_in_parallel
from app.agents.standards import BLOCKING_CHECKS
from app.graph.state import ProjectState
from app.security.agent_permissions import guard

QUALITY_SEVERITY = {"infeasibility": "high"}


def own_findings(state: ProjectState, found: dict) -> list[dict]:
    """Requirements this agent's own findings fail, in the shape the clarification step expects."""
    by_id = {r["id"]: r for r in state["requirements"]}
    roles = {i: r.get("stakeholder_role") for i, r in by_id.items()}
    failed: dict[str, list[dict]] = {}
    for f in found.get("quality_findings", []):
        if f["req_id"] in by_id:
            failed.setdefault(f["req_id"], []).append(
                {"check": f["check"], "message": f["explanation"], "severity": QUALITY_SEVERITY.get(f["check"], "medium")})
    for c in found.get("conflicts", []):
        if c["kind"] == "conflict":
            check = "conflicting_stakeholder_expectations" if len({roles.get(i) for i in c["req_ids"]} - {None}) > 1 \
                else "inconsistency"
            severity = "high"
        else:
            check, severity = "duplication", "medium"
        for i in c["req_ids"]:
            if i in by_id:
                failed.setdefault(i, []).append({"check": check, "message": c["description"], "severity": severity})
    return [{"req_id": i, "statement": by_id[i]["statement"], "stakeholder_role": by_id[i].get("stakeholder_role"),
             "categories": by_id[i]["categories"], "checks": checks,
             "blocking": any(c["check"] in BLOCKING_CHECKS and c["severity"] == "high" for c in checks)}
            for i, checks in failed.items()]


def review(state: ProjectState) -> ProjectState:
    found = run_steps_in_parallel([("quality_review", quality_review.quality_review),
                                   ("conflict_detection", conflict.conflict_detection),
                                   ("risk_analysis", risk.risk_analysis)], state)
    asked = guard("clarification", clarification.clarification)(
        state | found | {"returned": own_findings(state, found), "issues": []})
    return {"quality_findings": found.get("quality_findings", []), "conflicts": found.get("conflicts", []),
            "risks": found.get("risks", []), "clarifications": asked["clarifications"]}
