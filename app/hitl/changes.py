"""Change requests against the approved baseline (step 16: "changes to approved requirements").

Once a project has completed, its requirement baseline can only change through a change request:
  1. anyone in a catalog role proposes adding, modifying or removing a requirement, with a reason;
  2. a deterministic impact analysis lists what the change touches (dependent requirements, use cases, stories,
     tests, regulations, risks, workflow phases, artefacts to regenerate) and routes it to the accountable roles;
  3. every required role approves; any rejection closes it; "request changes" sends it back to the proposer;
  4. on approval the change is applied as a new requirement version (old versions kept), the graph state and the
     requirements table are updated, and the artefacts are marked stale until a human regenerates them.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.audit import record
from app.catalog.loader import get_catalog
from app.config import get_settings
from app.hitl.controls import ARCH_CATEGORIES, REGULATED_CATEGORIES
from app.models import ApprovalRequest, Project, Requirement


class ChangeError(ValueError):
    pass


def graph_config(project_id: int) -> dict:
    return {"configurable": {"thread_id": f"project-{project_id}-v2"}}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def completed_state(graph, project_id: int) -> dict:
    snap = graph.get_state(graph_config(project_id))
    if not snap.values or snap.next or any(i for t in snap.tasks for i in t.interrupts):
        raise ChangeError("Changes to approved requirements are made once the analysis has completed; "
                          "before that, edit requirements at the baseline gate")
    return snap.values


def impact_analysis(state: dict, action: str, req_id: str | None, categories: list[str]) -> dict:
    reqs = {r["id"]: r for r in state["requirements"]}
    target = reqs.get(req_id) if req_id else None
    cats = set(categories) | set(target["categories"] if target else [])
    arts = state.get("artifacts") or {}
    mappings = [m for m in state.get("compliance", {}).get("mappings", []) if req_id and m["req_id"] == req_id
                and (m.get("legal_decision") or {}).get("action") != "reject"]
    dependents = sorted(i for i, r in reqs.items() if req_id and req_id in r.get("depends_on", [])
                        and r.get("status") not in ("rejected", "suggested"))
    use_cases = [u["id"] for u in arts.get("use_cases", []) if req_id and req_id in u["requirement_ids"]]
    stories = [s["req_id"] for s in arts.get("user_stories", []) if s["req_id"] == req_id]
    risks = [rk["id"] for rk in state.get("risks", []) if req_id and req_id in rk["related_req_ids"]]
    phases = [p["name"] for p in state.get("sdlc_workflow", {}).get("phases", []) if req_id and req_id in p["requirement_ids"]]

    roles = list(get_settings().change_approvers)
    if cats & REGULATED_CATEGORIES or mappings:
        roles.append("compliance_legal")
    if cats & {"security", "privacy"}:
        roles.append("infosec")
    if cats & ARCH_CATEGORIES:
        roles.append("architect_developer")
    regenerate = ["requirements", "srs_markdown", "traceability_matrix"]
    regenerate += ["user_stories"] * bool(stories or action == "add") + ["use_cases", "process_workflows"] * bool(use_cases)
    regenerate += ["compliance_matrix"] * bool(mappings) + ["threat_risk_register"] * bool(risks)
    regenerate += ["data_requirements"] * bool(cats & {"data", "privacy"}) + ["interface_requirements"] * bool("integration" in cats)
    regenerate += ["assumptions_dependencies"] * bool(dependents or (target and target.get("depends_on")))
    level = "high" if mappings or cats & {"security", "privacy", "regulatory"} or len(dependents) > 2 else \
        "medium" if dependents or use_cases or risks else "low"
    return {
        "level": level, "categories": sorted(cats), "dependent_requirements": dependents,
        "depends_on": target.get("depends_on", []) if target else [], "use_cases": use_cases, "user_stories": stories,
        "acceptance_tests": len(target["acceptance_criteria"]) if target else 0,
        "regulations": sorted({m["regulation"] for m in mappings}), "risks": risks, "workflow_phases": phases,
        "artefacts_to_regenerate": list(dict.fromkeys(regenerate)), "required_roles": list(dict.fromkeys(roles)),
    }


def propose(session: Session, graph, project_id: int, body: dict) -> ApprovalRequest:
    state = completed_state(graph, project_id)
    reqs = {r["id"]: r for r in state["requirements"]}
    action, req_id = body["action"], body.get("req_id")
    if get_catalog().role(body["role"]) is None:
        raise ChangeError(f"Unknown role '{body['role']}'")
    if action in ("modify", "remove"):
        if req_id not in reqs or reqs[req_id].get("status") in ("rejected", "suggested"):
            raise ChangeError(f"'{req_id}' is not an approved requirement of this project")
    if action in ("add", "modify") and not (body.get("statement") or "").strip():
        raise ChangeError("A requirement statement is required")
    if action == "add" and not body.get("categories"):
        raise ChangeError("Give at least one category for a new requirement")
    imp = impact_analysis(state, action, req_id, body.get("categories") or [])
    title = {"add": "Add requirement", "modify": f"Modify {req_id}", "remove": f"Remove {req_id}"}[action]
    cr = ApprovalRequest(
        project_id=project_id, kind="change_request", title=title, required_roles=imp["required_roles"], decisions=[],
        created_by=body["requested_by"], created_role=body["role"], status="pending",
        payload={"action": action, "req_id": req_id, "statement": body.get("statement"), "reason": body["reason"],
                 "categories": body.get("categories") or [], "priority": body.get("priority") or "should",
                 "type": body.get("type") or "functional",
                 "current_statement": reqs[req_id]["statement"] if req_id else None, "impact": imp, "revisions": 0})
    session.add(cr)
    session.flush()
    record(project_id, body["requested_by"], "change_requested",
           {"cr": cr.id, "action": action, "req_id": req_id, "impact": imp["level"], "required_roles": imp["required_roles"]})
    return cr


def revise(cr: ApprovalRequest, statement: str, reason: str, by: str) -> None:
    if cr.status != "changes_requested":
        raise ChangeError("Only a change request sent back for changes can be revised")
    cr.payload = cr.payload | {"statement": statement, "reason": reason or cr.payload["reason"],
                               "revisions": cr.payload.get("revisions", 0) + 1}
    cr.decisions = [*cr.decisions, {"role": None, "reviewer": by, "decision": "revised", "at": _now().isoformat()}]
    cr.status = "pending"
    record(cr.project_id, by, "change_revised", {"cr": cr.id})


def current_decisions(cr: ApprovalRequest) -> dict[str, dict]:
    """Latest decision per role since the last revision."""
    latest: dict[str, dict] = {}
    for d in cr.decisions:
        if d["decision"] == "revised":
            latest = {}
        elif d["role"]:
            latest[d["role"]] = d
    return latest


def decide(session: Session, graph, cr: ApprovalRequest, reviewer: str, role: str, decision: str, comment: str) -> None:
    if cr.status != "pending":
        raise ChangeError(f"Change request is {cr.status}")
    if role not in cr.required_roles:
        raise ChangeError(f"Role '{role}' is not an approver of this change; expected one of {cr.required_roles}")
    if decision in ("reject", "request_changes") and not comment.strip():
        raise ChangeError("Give a reason when rejecting or requesting changes")
    cr.decisions = [*cr.decisions, {"role": role, "reviewer": reviewer, "decision": decision, "comment": comment,
                                    "at": _now().isoformat()}]
    record(cr.project_id, reviewer, f"change_{decision}", {"cr": cr.id, "role": role, "comment": comment})
    if decision == "reject":
        cr.status, cr.closed_at = "rejected", _now()
    elif decision == "request_changes":
        cr.status = "changes_requested"
    elif all(current_decisions(cr).get(r, {}).get("decision") == "approve" for r in cr.required_roles):
        apply(session, graph, cr)


def _new_id(state: dict, project_domain: str, req_type: str) -> str:
    domain = get_catalog().domain(project_domain)
    code = domain.code if domain else "GEN"
    prefix = "FR" if req_type == "functional" else "NFR"
    used = [int(r["id"].rsplit("-", 1)[-1]) for r in state["requirements"] if r["id"].startswith(f"{prefix}-{code}-")]
    return f"{prefix}-{code}-{max(used, default=0) + 1:03d}"


def apply(session: Session, graph, cr: ApprovalRequest) -> None:
    """Apply an approved change as a new requirement version, in the graph state and the requirements table."""
    state = completed_state(graph, cr.project_id)
    p, now = cr.payload, _now().isoformat()
    ref = f"CR-{cr.id}"
    reqs = list(state["requirements"])
    project = session.get(Project, cr.project_id)
    if p["action"] == "add":
        req_id = _new_id(state, project.domain, p["type"])
        new = {"id": req_id, "statement": p["statement"], "type": p["type"], "categories": p["categories"],
               "priority": p["priority"], "acceptance_criteria": [], "source_quote": "", "confidence": 1.0,
               "origin": "change_request", "status": "accepted", "stakeholder_role": cr.created_role, "source_id": None,
               "source_title": f"Change request {ref}", "source_type": None, "business_justification": p["reason"],
               "assumptions": [], "dependencies": [], "applicable_regulations": [], "risk_level": "low",
               "version": 1, "history": [], "change_request": ref}
        reqs.append(new)
        session.add(Requirement(project_id=cr.project_id, req_id=req_id, statement=p["statement"], req_type=p["type"],
                                categories=p["categories"], priority=p["priority"], acceptance_criteria=[], source_quote="",
                                confidence=1.0, approval_status="accepted", origin="change_request",
                                stakeholder_role=cr.created_role, business_justification=p["reason"], version=1, history=[]))
        cr.payload = p | {"req_id": req_id}
    else:
        req_id = p["req_id"]
        for i, r in enumerate(reqs):
            if r["id"] != req_id:
                continue
            version = r.get("version", 1)
            hist = [*r.get("history", []), {"version": version, "statement": r["statement"], "status": r.get("status"),
                                            "replaced_by": ref, "at": now}]
            if p["action"] == "modify":
                reqs[i] = r | {"statement": p["statement"], "status": "modified", "version": version + 1, "history": hist,
                               "change_request": ref}
            else:
                reqs[i] = r | {"status": "rejected", "removed_by": ref, "version": version + 1, "history": hist}
        row = session.query(Requirement).filter_by(project_id=cr.project_id, req_id=req_id).one_or_none()
        if row is not None:
            row.history = [*(row.history or []), {"version": row.version, "statement": row.statement,
                                                  "status": row.approval_status, "replaced_by": ref, "at": now}]
            row.version += 1
            if p["action"] == "modify":
                row.statement, row.approval_status = p["statement"], "modified"
            else:
                row.approval_status = "removed"
    graph.update_state(graph_config(cr.project_id), {"requirements": reqs}, as_node="documentation")
    project.status = "artifacts_stale"
    cr.status, cr.closed_at = "applied", _now()
    record(cr.project_id, "coordinator_agent", "change_applied",
           {"cr": cr.id, "action": p["action"], "req_id": req_id, "artefacts_to_regenerate": p["impact"]["artefacts_to_regenerate"]})
