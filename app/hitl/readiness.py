"""Production-readiness reviews (step 16: "production-readiness decisions").

Before a release goes to production, the readiness approvers (project manager, operations, information security,
compliance & legal by default) each give a go, conditional go or no-go decision. The review carries a checklist:
  - automatic checks, evaluated from the project's approved state each time someone decides (e.g. every
    regulatory interpretation decided, mandatory controls in the workflow, no pending change requests);
  - attestations that only a person can give (tests passed, penetration test closed, runbooks and DR tested,
    regulatory obligations evidenced).
Each item has an owner role. A role can only say "go" when its own items pass, are attested by it, or are waived by
it with a written justification. Any no-go rejects the review; go from every role approves it.
"""

import copy
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record
from app.config import get_settings
from app.hitl.changes import ChangeError, completed_state
from app.hitl.controls import decision_items
from app.models import ApprovalRequest, Project


ATTESTATIONS = [
    ("tests_passed", "All planned tests executed and passed, including transaction-integrity and regression suites", "project_manager"),
    ("uat_signed_off", "User acceptance testing signed off by the business", "project_manager"),
    ("security_testing_closed", "SAST clean and penetration-test findings closed or formally accepted", "infosec"),
    ("operational_readiness", "Runbooks, monitoring, alerting, backup/restore and rollback plan tested", "operations"),
    ("compliance_evidence", "Evidence for every regulatory obligation in scope is filed and approved", "compliance_legal"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def automatic_checks(state: dict, project: Project, open_changes: int) -> list[dict]:
    s = get_settings()

    def approved(approvals: list[dict], roles: list[str]) -> bool:
        return set(roles) <= {a["role"] for a in approvals if a["decision"] == "approve"}

    items = decision_items(state)
    undecided = [i for i, it in items.items() if not it["decided"]]
    interp = [m for m in state.get("compliance", {}).get("mappings", []) if m.get("needs_legal_review")]
    open_legal = [m["id"] for m in interp if not m.get("legal_decision")]
    wf = state.get("sdlc_workflow", {})
    # Same rules as the workflow generator: anything it would still have to add is missing.
    from app.agents.workflow import enforce_controls
    missing_controls = [c["control"] for c in enforce_controls(copy.deepcopy(wf.get("phases", [])), state)]         if wf.get("phases") else ["no workflow"]
    blocking = [q["question"] for q in state.get("clarifications", []) if q["severity"] == "blocking"]

    def check(cid: str, label: str, owner: str, ok: bool, evidence: str) -> dict:
        return {"id": cid, "label": label, "kind": "automatic", "owner": owner, "status": "pass" if ok else "fail",
                "evidence": evidence}

    return [
        check("baseline_approved", "Requirement baseline approved by all required roles", "project_manager",
              bool(state.get("baseline_approvals")) and project.status in ("completed", "artifacts_stale"),
              f"{sum(a['decision'] == 'approve' for a in state.get('baseline_approvals', []))} baseline approvals"),
        check("decisions_recorded", "Every requirement needing a human decision has one", "project_manager", not undecided,
              f"{len(items) - len(undecided)}/{len(items)} decided" + (f"; open: {', '.join(undecided)}" if undecided else "")),
        check("legal_interpretations", "Every regulatory interpretation decided by compliance & legal", "compliance_legal",
              not open_legal, f"{len(interp) - len(open_legal)}/{len(interp)} decided"),
        check("sdlc_approved", "SDLC selection approved by all four roles", "project_manager",
              approved(state.get("sdlc_approvals", []), s.sdlc_approvers), f"model: {state.get('sdlc_decision', {}).get('model')}"),
        check("workflow_approved", "Project workflow approved", "project_manager",
              approved(state.get("workflow_approvals", []), s.workflow_approvers), f"{len(wf.get('phases', []))} phases"),
        check("mandatory_controls", "Mandatory security and compliance controls are in the workflow", "infosec",
              not missing_controls, "all present" if not missing_controls else f"missing: {', '.join(missing_controls)}"),
        check("no_blocking_questions", "No blocking clarification question left unanswered", "project_manager", not blocking,
              f"{len(blocking)} open"),
        check("no_pending_changes", "No change request pending", "project_manager", open_changes == 0, f"{open_changes} pending"),
        check("artefacts_current", "Documents regenerated after the last approved change", "project_manager",
              project.status == "completed", f"project status: {project.status}"),
    ]


def build_checklist(state: dict, project: Project, open_changes: int, previous: list[dict] | None = None) -> list[dict]:
    prev = {i["id"]: i for i in previous or []}
    checks = automatic_checks(state, project, open_changes)
    for c in checks:  # a waiver given earlier still applies while the check keeps failing
        if c["status"] == "fail" and prev.get(c["id"], {}).get("waiver"):
            c["status"], c["waiver"] = "waived", prev[c["id"]]["waiver"]
    attest = [prev.get(cid) or {"id": cid, "label": label, "kind": "attestation", "owner": owner, "status": "pending"}
              for cid, label, owner in ATTESTATIONS]
    return checks + attest


def _open_changes(session: Session, project_id: int) -> int:
    return len(session.scalars(select(ApprovalRequest).where(
        ApprovalRequest.project_id == project_id, ApprovalRequest.kind == "change_request",
        ApprovalRequest.status.in_(("pending", "changes_requested")))).all())


def open_review(session: Session, graph, project_id: int, release: str, by: str, role: str) -> ApprovalRequest:
    state = completed_state(graph, project_id)
    project = session.get(Project, project_id)
    if role not in get_settings().readiness_approvers:
        raise ChangeError(f"Readiness reviews are opened by one of {get_settings().readiness_approvers}")
    review = ApprovalRequest(project_id=project_id, kind="production_readiness", title=f"Production readiness — {release}",
                             required_roles=list(get_settings().readiness_approvers), decisions=[], status="pending",
                             created_by=by, created_role=role,
                             payload={"release": release, "checklist": build_checklist(state, project, _open_changes(session, project_id))})
    session.add(review)
    session.flush()
    record(project_id, by, "readiness_review_opened", {"review": review.id, "release": release})
    return review


def decide(session: Session, graph, review: ApprovalRequest, reviewer: str, role: str, decision: str, comment: str,
           attest: list[str], waivers: dict[str, str]) -> None:
    if review.status != "pending":
        raise ChangeError(f"Review is {review.status}")
    if role not in review.required_roles:
        raise ChangeError(f"Role '{role}' is not a readiness approver; expected one of {review.required_roles}")
    state = completed_state(graph, review.project_id)
    project = session.get(Project, review.project_id)
    checklist = build_checklist(state, project, _open_changes(session, review.project_id), review.payload["checklist"])
    by_id = {i["id"]: i for i in checklist}
    for cid in attest:
        item = by_id.get(cid)
        if not item or item["kind"] != "attestation":
            raise ChangeError(f"'{cid}' is not an attestation item")
        if item["owner"] != role:
            raise ChangeError(f"'{cid}' must be attested by {item['owner']}")
        item |= {"status": "pass", "attested_by": reviewer, "at": _now()}
    for cid, why in waivers.items():
        item = by_id.get(cid)
        if not item or item["status"] != "fail":
            raise ChangeError(f"'{cid}' is not a failing check")
        if item["owner"] != role:
            raise ChangeError(f"'{cid}' can only be waived by {item['owner']}")
        if not why.strip():
            raise ChangeError("A waiver needs a written justification")
        item |= {"status": "waived", "waiver": {"by": reviewer, "role": role, "justification": why, "at": _now()}}
    if decision in ("go", "conditional"):
        blocking = [i["id"] for i in checklist if i["owner"] == role and i["status"] in ("fail", "pending")]
        if blocking:
            raise ChangeError(f"Resolve, attest or waive your items before deciding go: {', '.join(blocking)}")
    if decision in ("no_go", "conditional") and not comment.strip():
        raise ChangeError("Give the reasons for a no-go, or the conditions for a conditional go")
    review.payload = review.payload | {"checklist": checklist}
    review.decisions = [*review.decisions, {"role": role, "reviewer": reviewer, "decision": decision, "comment": comment,
                                            "attested": attest, "waived": list(waivers), "at": _now()}]
    record(review.project_id, reviewer, f"readiness_{decision}", {"review": review.id, "role": role, "comment": comment,
                                                                   "attested": attest, "waived": list(waivers)})
    latest = {d["role"]: d["decision"] for d in review.decisions}
    if decision == "no_go":
        review.status, review.closed_at = "rejected", datetime.now(timezone.utc)
    elif all(latest.get(r) in ("go", "conditional") for r in review.required_roles):
        review.status = "approved_with_conditions" if "conditional" in latest.values() else "approved"
        review.closed_at = datetime.now(timezone.utc)
        record(review.project_id, "human_approval_agent", "production_readiness_decided",
               {"review": review.id, "status": review.status})
