"""SDLC-workflow agent (step 15): customises the approved SDLC model into a project-specific workflow.

The chosen model fixes the structure: its canonical phases, what each phase does (kinds) and when it recurs
(once, every iteration, every release, every cycle, continuously), and how security, testing, compliance, approvals
and traceability normally run under it (sdlc_models.yaml `execution`). The LLM fills every canonical phase with
project-specific content and proposes durations and iteration counts. Deterministic rules then:
  - keep the model's phases (a missing phase is added, an invented one is dropped);
  - schedule the timeline from the model's structure (app/rules/workflow.py) and draw a Gantt chart;
  - enforce mandatory financial-sector controls in the phase of the right kind (threat modelling in design, SAST in
    implementation, transaction-integrity testing in testing, compliance approval before deployment, audit-trail tests);
  - add the traceability each phase kind must maintain, and normalise approver roles;
  - make the last release-type gate the production-readiness approval (human-in-the-loop control, step 16).
The result goes to the workflow-approval gate, where humans accept, modify or ask for regeneration.
"""

import copy

from app import llm
from app.agents.common import domain_name, format_requirements, role_name
from app.agents.sdlc import baseline, factor_signals
from app.audit import record
from app.catalog.loader import get_catalog
from app.config import get_settings
from app.graph.state import ProjectState
from app.rules.sdlc import load_sdlc_catalog
from app.rules.workflow import (TRACEABILITY_BY_KIND, build_schedule, gantt, normalise_roles, project_start,
                                schedule_params, timing_label)
from app.schemas import SdlcWorkflow

COMPONENTS = ("activities", "security", "testing", "compliance", "approvals", "traceability")
LIST_FIELDS = ("activities", "responsible_roles", "deliverables", "security_activities", "testing",
               "compliance_checkpoints", "entry_criteria", "exit_criteria", "traceability")
FINANCIAL_DOMAINS = ("payments", "loan_processing", "digital_banking", "kyc_onboarding", "trade_finance")

WORKFLOW_PROMPT = """Customise the {model} SDLC into a project-specific workflow for this {domain} project at a bank.
{feedback}
How {model} runs ({structure}): {cadence}
Canonical phases, in order (fill EVERY phase, use these names exactly, do not add phases):
{phases}

How each component normally runs under {model}:
{norms}

For every phase give: objective; activities; responsible roles (from: {roles}); deliverables; security activities;
testing requirements; compliance checkpoints; entry and exit criteria; a human approval gate (name, approver roles,
pass criteria); traceability (which trace links the phase creates or verifies); duration_weeks for ONE occurrence of the
phase; and the baseline requirement IDs mainly delivered or verified in it.
Also give: the timeline settings ({timeline_hint}); a component_plan saying, for this project, how each of
activities, security, testing, compliance, approvals and traceability runs under {model} and when; the cadence; and a
one-line traceability summary.
Be concrete and specific to this project (e.g. "threat model the credit-bureau integration", "reconcile disbursements
against core banking"), not generic. Respect the schedule and budget signals.

Schedule and budget signals: {schedule}
Regulations to evidence: {regulations}
Top risks: {risks}
Requirements:
{requirements}"""


def _model(state: ProjectState) -> dict:
    cat = load_sdlc_catalog()
    return next((m for m in cat["models"] if m["name"] == state["sdlc_decision"]["model"]), cat["models"][0])


def _of_kind(phases: list[dict], *kinds: str, last: bool = False) -> list[dict]:
    """Phases of the first matching kind; the target phase (first, or last with last=True) comes first."""
    for k in kinds:
        hits = [p for p in phases if k in p["kinds"]]
        if hits:
            return hits[::-1] if last else hits
    return phases[-1:]


def _mentions(phases: list[dict], *words: str) -> bool:
    text = " ".join(" ".join([*p["activities"], *p["security_activities"], *p["testing"], *p["compliance_checkpoints"],
                              p["approval_gate"]["name"], *p["approval_gate"]["criteria"]]) for p in phases).lower()
    return any(w in text for w in words)


# What enforce_controls() guarantees, for display (keep in step with the code below).
MANDATORY_CONTROLS = [
    {"control": "Threat modelling (STRIDE) of new features and integrations", "phase": "design",
     "when": "the baseline has security or privacy requirements"},
    {"control": "Static application security testing (SAST) and dependency scanning on every change", "phase": "implementation",
     "when": "always"},
    {"control": "Transaction-integrity and reconciliation testing (amounts, idempotency, duplicates, reversals)",
     "phase": "testing / validation", "when": "financial domains (loans, KYC, payments, banking)"},
    {"control": "Verify audit-trail completeness for every state change", "phase": "testing / validation",
     "when": "the baseline has audit requirements"},
    {"control": "Compliance officer approval of regulatory requirements before deployment", "phase": "release",
     "when": "the baseline has regulatory requirements (compliance & legal is added to the release gate)"},
    {"control": "Production-readiness review (go / no-go)", "phase": "last release gate", "when": "always"},
]


def enforce_controls(phases: list[dict], state: ProjectState) -> list[dict]:
    """Mandatory controls for financial systems, placed in the phase whose kind they belong to (step 15 example)."""
    cats = {c for r in baseline(state) for c in r["categories"]}
    added = []

    def add(targets: list[dict], field: str, item: str, reason: str) -> None:
        phase = targets[0]
        phase[field].append(item)
        added.append({"phase": phase["name"], "field": field, "control": item, "reason": reason})

    design = _of_kind(phases, "design", "risk", "plan")
    if {"security", "privacy"} & cats and not _mentions(design, "threat model"):
        add(design, "security_activities", "Threat modelling (STRIDE) of new features and integrations",
            "Security/privacy requirements present: threat modelling during design")
    build = _of_kind(phases, "implementation")
    if not _mentions(build, "static", "sast"):
        add(build, "security_activities", "Static application security testing (SAST) and dependency scanning on every change",
            "Secure SDLC baseline: static security testing during implementation")
    test = _of_kind(phases, "testing", "validation", last=True)  # system-level testing, e.g. V-Model system testing
    if state["domain"] in FINANCIAL_DOMAINS and not _mentions(test, "transaction integrity", "transaction-integrity", "reconcil"):
        add(test, "testing", "Transaction-integrity and reconciliation testing (amounts, idempotency, duplicates, reversals)",
            "Financial transactions in scope: transaction-integrity testing during validation")
    if "audit" in cats and not _mentions(test, "audit trail", "audit-trail", "audit log"):
        add(test, "testing", "Verify audit-trail completeness for every state change", "Audit requirements present")
    release = _of_kind(phases, "release", last=True)  # the gate right before deployment
    if "regulatory" in cats and not _mentions(release, "compliance approval", "compliance sign-off", "compliance officer"):
        add(release, "compliance_checkpoints", "Compliance officer approval of regulatory requirements before deployment",
            "Regulatory requirements present: compliance approval before deployment")
        gate = release[0]["approval_gate"]
        if "compliance_legal" not in gate["approvers"]:
            gate["approvers"].append("compliance_legal")
        gate["criteria"].append("Compliance officer has approved the regulatory requirements in this release")
    return added


def _stub(canonical: dict, model: dict) -> dict:
    return {"name": canonical["name"], "objective": f"{canonical['name']} ({model['name']})", "activities": [],
            "responsible_roles": ["project_manager"], "deliverables": [], "security_activities": [], "testing": [],
            "compliance_checkpoints": [], "entry_criteria": [], "exit_criteria": [], "traceability": [],
            "duration_weeks": 1.0, "requirement_ids": [],
            "approval_gate": {"name": f"{canonical['name']} sign-off", "approvers": ["project_manager"], "criteria": []}}


def finalise(raw: dict, model: dict, state: ProjectState, schedule_override: dict | None = None) -> dict:
    """Apply the deterministic rules to a generated (or human-edited) workflow. Idempotent."""
    ids = {r["id"] for r in baseline(state)}
    by_name = {p["name"].strip().lower(): p for p in raw.get("phases", [])}
    phases, added_phases = [], []
    for c in model["phases"]:
        p = by_name.get(c["name"].lower())
        if p is None:  # the LLM renamed or skipped a canonical phase
            p = _stub(c, model)
            added_phases.append(c["name"])
        p = copy.deepcopy(p) | {"name": c["name"], "kinds": c["kinds"], "recurrence": c["recurrence"]}
        if c.get("pairs_with"):
            p["pairs_with"] = c["pairs_with"]
        p["requirement_ids"] = [i for i in p.get("requirement_ids", []) if i in ids]
        p["responsible_roles"] = normalise_roles(p.get("responsible_roles", [])) or ["project_manager"]
        gate = p["approval_gate"]
        gate["approvers"] = [a for a in normalise_roles(gate.get("approvers", [])) if get_catalog().role(a)] or ["project_manager"]
        for k in c["kinds"]:  # traceability each kind of phase must maintain
            rule = TRACEABILITY_BY_KIND.get(k)
            if rule and rule not in p.setdefault("traceability", []):
                p["traceability"].append(rule)
        phases.append(p)
    dropped = [p["name"] for p in raw.get("phases", []) if p["name"].strip().lower() not in {c["name"].lower() for c in model["phases"]}]
    for name in (c["pairs_with"] for c in model["phases"] if c.get("pairs_with")):  # V-Model: tests designed on the left
        left = next(c["name"] for c in model["phases"] if c.get("pairs_with") == name)
        right = next((p for p in phases if p["name"] == name), None)
        if right is not None:
            right["designed_in"] = left

    controls = enforce_controls(phases, state)

    # Human-in-the-loop (step 16): the last release-type gate is the production-readiness decision.
    readiness = get_settings().readiness_approvers
    release = [p for p in phases if "release" in p["kinds"]] or phases[-1:]
    gate = release[-1]["approval_gate"]
    gate["approvers"] = list(dict.fromkeys([*gate["approvers"], *readiness]))
    criterion = "Production-readiness review approved (go decision by " + ", ".join(role_name(r) for r in readiness) + ")"
    if criterion not in gate["criteria"]:
        gate["criteria"].append(criterion)
    gate["hitl_control"] = "production_readiness"

    params = schedule_params({**{k: raw.get(k) for k in ("iterations", "iteration_length_weeks", "iterations_per_release",
                                                           "cycles")}, **(schedule_override or {})}, model["execution"])
    sched = build_schedule(phases, model["execution"]["structure"], params)
    start = project_start()
    for p in phases:
        p["duration_weeks"] = round(max(0.2, min(26.0, float(p.get("duration_weeks") or 1.0))), 1)
        p["occurrences"] = sched["occurrences"][p["name"]]
        p["timing"] = timing_label(p, p["occurrences"], params)

    plan = {c["component"]: c["how"] for c in raw.get("component_plan", []) if c.get("how")}
    norms = model["execution"]["components"]
    component_plan = [{"component": c, "how": plan.get(c) or norms.get(c, ""), "model_norm": norms.get(c, ""),
                       "source": "project" if plan.get(c) else "model default"} for c in COMPONENTS]
    return {
        "model": model["name"], "structure": model["execution"]["structure"], "phases": phases,
        "cadence": raw.get("cadence") or model["execution"]["cadence"], "model_cadence": model["execution"]["cadence"],
        "traceability": raw.get("traceability", ""), "component_plan": component_plan,
        "schedule": params | {"start_date": start.isoformat(), "total_weeks": sched["total_weeks"]},
        "gantt": gantt(model["name"], phases, sched["occurrences"], start),
        "controls_added_by_rules": controls, "phases_added_by_rules": added_phases, "phases_dropped": dropped,
        "requirements_not_assigned": sorted(ids - {i for p in phases for i in p["requirement_ids"]}),
    }


def sdlc_workflow(state: ProjectState) -> ProjectState:
    model = _model(state)
    domain = get_catalog().domain(state["domain"])
    reqs = baseline(state)
    regulations = sorted({m["regulation"] for m in state.get("compliance", {}).get("mappings", [])
                          if (m.get("legal_decision") or {}).get("action") != "reject"}) \
        or (domain.typical_regulations if domain else [])
    ex = model["execution"]
    timeline_hint = {"cyclic": "cycles", "sequential": "none; durations only", "v_paired": "none; durations only"}.get(
        ex["structure"], "iterations, iteration_length_weeks, iterations_per_release")
    approvals = state.get("workflow_approvals", [])
    feedback = f"Reviewer feedback on the previous workflow (address it):\n{state['feedback']}\n" \
        if approvals and approvals[-1].get("decision") == "regenerate" and state.get("feedback") else ""
    signals = factor_signals(state)
    result = llm.structured(SdlcWorkflow, WORKFLOW_PROMPT.format(
        model=model["name"], domain=domain_name(state["domain"]), feedback=feedback, structure=ex["structure"],
        cadence=ex["cadence"],
        phases="\n".join(f"- {p['name']} (does: {', '.join(p['kinds'])}; runs: {p['recurrence'].replace('_', ' ')}"
                         + (f"; its tests are executed in {p['pairs_with']}" if p.get("pairs_with") else "") + ")"
                         for p in model["phases"]),
        norms="\n".join(f"- {k}: {v}" for k, v in ex["components"].items()),
        roles=", ".join(f"{r.id} ({r.name})" for r in get_catalog().roles), timeline_hint=timeline_hint,
        schedule={"statements": signals["schedule_budget_statements"],
                  "budget_schedule_constraint": state.get("factors", {}).get("budget_schedule_constraint"),
                  "defaults": {k: ex[k] for k in ("iterations", "iteration_length_weeks", "iterations_per_release", "cycles") if k in ex}},
        regulations="; ".join(regulations) or "none identified",
        risks="; ".join(f"{r['id']} {r['title']}" for r in state.get("risks", [])[:6]) or "none",
        requirements=format_requirements(reqs)))
    raw = result.model_dump()
    workflow = finalise(raw, model, state)
    workflow["generated"] = raw  # kept so human edits can be re-finalised against the original
    record(state["project_id"], "planning_agent", "workflow_generated",
           {"model": model["name"], "phases": len(workflow["phases"]), "total_weeks": workflow["schedule"]["total_weeks"],
            "controls_added": len(workflow["controls_added_by_rules"]), "phases_added": workflow["phases_added_by_rules"],
            "phases_dropped": workflow["phases_dropped"], "unassigned": len(workflow["requirements_not_assigned"])})
    return {"sdlc_workflow": workflow, "workflow_approvals": []}


def apply_workflow_edits(state: ProjectState, edits: list[dict], schedule: dict) -> tuple[dict, list[dict]]:
    """Apply human edits to the workflow, then re-run the deterministic rules (mandatory controls cannot be removed)."""
    wf = state["sdlc_workflow"]
    raw = copy.deepcopy({"phases": wf["phases"], "cadence": wf["cadence"], "traceability": wf["traceability"],
                         "component_plan": [{"component": c["component"], "how": c["how"]} for c in wf["component_plan"]
                                            if c["source"] == "project"],
                         **{k: wf["schedule"].get(k) for k in ("iterations", "iteration_length_weeks",
                                                               "iterations_per_release", "cycles")}})
    applied = []
    for e in edits:
        phase = next((p for p in raw["phases"] if p["name"] == e["phase"]), None)
        if phase is None:
            continue
        if e["field"] == "duration_weeks":
            phase["duration_weeks"] = float(e["value"])
        elif e["field"] == "objective":
            phase["objective"] = str(e["value"])
        elif e["field"] in LIST_FIELDS:
            values = e["value"] if isinstance(e["value"], list) else [str(e["value"])]
            phase[e["field"]] = [v.strip() for v in values if str(v).strip()]
        applied.append(e)
    model = _model(state)
    out = finalise(raw, model, state, schedule_override=schedule)

    def present(c: dict) -> bool:
        return any(p["name"] == c["phase"] and c["control"] in p[c["field"]] for p in out["phases"])
    kept = [c for c in wf.get("controls_added_by_rules", []) if present(c)]
    out["controls_added_by_rules"] = kept + [c for c in out["controls_added_by_rules"] if c not in kept]
    out["generated"] = wf.get("generated")
    out["human_edits"] = [*wf.get("human_edits", []), *applied]
    return out, applied
