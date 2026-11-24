"""Which AI outputs need an explicit human decision, and which role owns that decision.

Step 16 makes human approval mandatory for eight kinds of decision. Five are taken inside the analysis graph:
  1 final requirement baselines      baseline_approval gate (all required roles approve)
  2 regulatory interpretations       per-mapping legal decision by compliance & legal, at the baseline gate
  3 high-risk security requirements  per-requirement decision by information security, at the baseline gate
  4 conflicting stakeholder decisions per-requirement decision by the baseline owner, at the baseline gate
  5 architecture-critical requirements per-requirement decision by the architect, at the baseline gate
  6 SDLC selection                   sdlc_approval gate (project manager, architect, security, compliance)
and two after the graph has finished (app/hitl/changes.py, app/hitl/readiness.py):
  7 changes to approved requirements change requests with impact analysis and role-based approval
  8 production-readiness decisions   go / no-go review against a readiness checklist
The generated workflow (step 15) also has its own approval gate.
"""

from app.config import get_settings

DECIDED = ("accepted", "modified", "rejected")
ARCH_CATEGORIES = {"integration", "performance", "availability"}
REGULATED_CATEGORIES = {"regulatory", "privacy", "audit"}

CONTROL_POINTS = [
    {"id": "baseline", "name": "Final requirement baseline", "where": "Baseline approval gate",
     "who": "Baseline owner plus the roles the content requires", "actions": "accept, reject, modify each requirement; approve; regenerate"},
    {"id": "regulatory_interpretations", "name": "Regulatory interpretations", "where": "Baseline approval gate, Compliance tab",
     "who": "Compliance & legal", "actions": "accept, reject or modify each interpretation; regenerate the baseline"},
    {"id": "high_risk_security", "name": "High-risk security requirements", "where": "Baseline approval gate",
     "who": "Information security", "actions": "accept, reject or modify each requirement"},
    {"id": "stakeholder_conflicts", "name": "Conflicting stakeholder decisions", "where": "Baseline approval gate",
     "who": "Baseline owner (product owner)", "actions": "accept, reject or modify each conflicting requirement"},
    {"id": "architecture_critical", "name": "Architecture-critical requirements", "where": "Baseline approval gate",
     "who": "Architect", "actions": "accept, reject or modify each requirement"},
    {"id": "sdlc_selection", "name": "SDLC selection", "where": "SDLC approval gate",
     "who": "Project manager, architect, information security, compliance & legal",
     "actions": "approve the recommendation, choose another model (with justification), correct the inputs and re-rank, regenerate"},
    {"id": "workflow", "name": "Project SDLC workflow", "where": "Workflow approval gate",
     "who": "Project manager, information security, compliance & legal", "actions": "approve, modify phases and timeline, regenerate"},
    {"id": "requirement_changes", "name": "Changes to approved requirements", "where": "Change requests (after completion)",
     "who": "Product owner, project manager and the roles the change affects", "actions": "approve, reject, request changes"},
    {"id": "production_readiness", "name": "Production-readiness decisions", "where": "Readiness reviews (after completion)",
     "who": "Project manager, operations, information security, compliance & legal", "actions": "go, no-go, conditional go; attest; waive with justification"},
]


def stakeholder_conflicts(state: dict) -> dict[str, list[str]]:
    """Requirement id -> the requirements it conflicts with, for conflicts between different stakeholder roles."""
    roles = {r["id"]: r.get("stakeholder_role") for r in state.get("requirements", [])}
    out: dict[str, list[str]] = {}
    for c in state.get("conflicts", []):
        if c["kind"] != "conflict" or len({roles.get(i) for i in c["req_ids"]} - {None}) < 2:
            continue
        for i in c["req_ids"]:
            out.setdefault(i, []).extend(x for x in c["req_ids"] if x != i)
    return out


def architecture_critical(r: dict) -> bool:
    return r.get("origin", "extracted") == "extracted" and r["priority"] == "must" and bool(ARCH_CATEGORIES & set(r["categories"]))


def decision_items(state: dict) -> dict[str, dict]:
    """Requirements that need an explicit accept / reject / modify decision, with the role that owns it.

    Ownership (first match): compliance & legal for regulatory interpretations and contradictions of approved
    sources; information security for high-risk security; the baseline owner for conflicts between stakeholders;
    the architect for architecture-critical requirements; the baseline owner for any other escalation.
    """
    owner_of = get_settings().baseline_owner_role
    conflicts = stakeholder_conflicts(state)
    items: dict[str, dict] = {}
    for r in state.get("requirements", []):
        reasons: list[tuple[str, str]] = []  # (owner role, reason)
        origin = r.get("origin", "extracted")
        if origin == "compliance_agent":
            reasons.append(("compliance_legal", "proposed by the compliance agent to close a compliance gap (regulatory interpretation)"))
        if r.get("escalated") and (r.get("grounding_support") == "contradicts_evidence" or REGULATED_CATEGORIES & set(r["categories"])):
            reasons.append(("compliance_legal", "escalated: " + "; ".join(r.get("escalation_reasons", []))))
        if (origin == "security_privacy_agent" and r.get("risk_level") == "high") or \
                (origin == "extracted" and "security" in r["categories"] and r.get("risk_level") == "high"):
            reasons.append(("infosec", "high-risk security requirement"))
        if r["id"] in conflicts:
            reasons.append((owner_of, "conflicts with another stakeholder's requirement: " + ", ".join(sorted(set(conflicts[r["id"]])))))
        if architecture_critical(r):
            reasons.append(("architect_developer", "architecture-critical (must-have integration, performance or availability)"))
        if r.get("escalated") and not any(o == "compliance_legal" for o, _ in reasons):
            reasons.append((owner_of, "escalated: " + "; ".join(r.get("escalation_reasons", []))))
        if not reasons or (r.get("status") == "suggested" and origin not in ("compliance_agent", "security_privacy_agent")):
            continue
        items[r["id"]] = {"owner": reasons[0][0], "reasons": [why for _, why in reasons],
                          "controls": sorted({_control(o, why) for o, why in reasons}),
                          "decided": r.get("status") in DECIDED}
    return items


def _control(owner: str, why: str) -> str:
    if why.startswith("conflicts"):
        return "stakeholder_conflicts"
    if owner == "compliance_legal":
        return "regulatory_interpretations"
    if owner == "infosec":
        return "high_risk_security"
    if owner == "architect_developer":
        return "architecture_critical"
    return "baseline"


def interpretations(state: dict) -> list[dict]:
    """Compliance mappings whose interpretation needs a compliance & legal decision."""
    return [m for m in state.get("compliance", {}).get("mappings", []) if m.get("needs_legal_review")]


def undecided(items: dict[str, dict], role: str, edits: list[dict]) -> list[str]:
    decided_now = {e["id"] for e in edits}
    return [i for i, it in items.items() if it["owner"] == role and not it["decided"] and i not in decided_now]


def register(state: dict, requests: list[dict]) -> list[dict]:
    """Status of every human-in-the-loop control for one project, with the evidence (who decided, when)."""
    s = get_settings()
    items = decision_items(state) if state.get("requirements") else {}

    def approvals(key: str, roles: list[str]) -> dict:
        done = {a["role"]: a for a in state.get(key, []) if a["decision"] == "approve"}
        status = "approved" if roles and set(roles) <= set(done) else ("pending" if state.get(key) is not None else "not reached")
        return {"status": status, "required_roles": roles, "evidence": [f"{a['role']}: {a['reviewer']} ({a['at']})" for a in done.values()]}

    def owned(control: str) -> dict:
        mine = {i: it for i, it in items.items() if control in it["controls"]}
        if not mine:
            return {"status": "not applicable", "evidence": []}
        open_ = [i for i, it in mine.items() if not it["decided"]]
        reqs = {r["id"]: r for r in state["requirements"]}
        return {"status": "pending" if open_ else "decided", "open": open_,
                "evidence": [f"{i}: {reqs[i].get('decision', {}).get('action', reqs[i].get('status'))} by "
                             f"{reqs[i].get('decision', {}).get('by', '?')}" for i, it in mine.items() if it["decided"]]}

    interp = interpretations(state)
    open_interp = [m["id"] for m in interp if not m.get("legal_decision")]
    baseline_roles = list(dict.fromkeys(a["role"] for a in state.get("baseline_approvals", []) if a["decision"] == "approve"))
    crs = [r for r in requests if r["kind"] == "change_request"]
    reviews = [r for r in requests if r["kind"] == "production_readiness"]
    status = {
        "baseline": {"status": "approved" if state.get("sdlc_recommendations") else ("pending" if state.get("requirements") else "not reached"),
                     "evidence": [f"approved by {', '.join(baseline_roles)}"] if baseline_roles else []},
        "regulatory_interpretations": {"status": "not applicable" if not interp else ("pending" if open_interp else "decided"),
                                       "open": open_interp,
                                       "evidence": [f"{m['id']}: {m['legal_decision']['action']} by {m['legal_decision']['by']}"
                                                    for m in interp if m.get("legal_decision")]},
        "high_risk_security": owned("high_risk_security"),
        "stakeholder_conflicts": owned("stakeholder_conflicts"),
        "architecture_critical": owned("architecture_critical"),
        "sdlc_selection": approvals("sdlc_approvals", s.sdlc_approvers),
        "workflow": approvals("workflow_approvals", s.workflow_approvers),
        "requirement_changes": {"status": f"{sum(r['status'] in ('pending', 'changes_requested') for r in crs)} open",
                                "evidence": [f"CR-{r['id']} {r['title']}: {r['status']}" for r in crs]},
        "production_readiness": {"status": reviews[-1]["status"] if reviews else "not requested",
                                 "evidence": [f"#{r['id']} {r['title']}: {r['status']}" for r in reviews]},
    }
    return [c | status[c["id"]] for c in CONTROL_POINTS]
