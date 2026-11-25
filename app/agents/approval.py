"""Human approval gates, run by the coordinator: decide WHO must approve, pause the graph (interrupt) and apply
human decisions.

Two gates in the analysis graph (step 16, see guide/human_in_the_loop.md), each with two steps:
  requirements_gate   "Approve requirements"
    1. clarification  only when there are blocking questions (once per pass, at most max_clarification_rounds)
    2. baseline       sign-off by every required role
  plan_gate           "Approve plan"
    1. sdlc           the SDLC model
    2. workflow       the project workflow built for that model

The steps:
  clarification_gate  questions routed to stakeholder roles: answer (accept), leave unanswered (reject), or ask for the
                      analysis to be regenerated with feedback
  baseline_approval   requirement baseline. Loops until every required role has approved. Requirements that are
                      high-risk security, architecture-critical, in conflict between stakeholders, escalated, or
                      proposed to close a compliance gap need an explicit accept / reject / modify from the role that
                      owns them; regulatory interpretations need an explicit accept / reject / modify from compliance
  sdlc_approval       SDLC selection; approve, choose another model (with justification), re-rank or regenerate
  workflow_approval   project-specific workflow; approve, modify phases and timeline, or regenerate

After the graph: change requests (app/hitl/changes.py) and production-readiness reviews (app/hitl/readiness.py).
Free text in resume values is masked by the API before it reaches the graph (and its checkpoints).
"""

from collections import defaultdict
from datetime import datetime, timezone

from langgraph.types import interrupt

from app.agents.common import role_name
from app.audit import record
from app.config import get_settings
from app.graph.state import ProjectState
from app.hitl.controls import decision_items, interpretations
from app.ingestion.service import ingest, questionnaire_to_text


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- Clarification gate ----------

def clarification_gate(state: ProjectState) -> ProjectState:
    questions = state.get("clarifications", [])
    by_role: dict[str, list[dict]] = defaultdict(list)
    for q in questions:
        by_role[q["target_role"]].append(q)
    round_no = state.get("clarification_round", 0) + 1
    response = interrupt({
        "gate": "clarification", "round": round_no, "max_rounds": get_settings().max_clarification_rounds,
        "questions": questions, "by_role": dict(by_role),
    })
    responder = response.get("responder", "analyst")
    if response.get("decision") == "regenerate":  # the questions themselves are not useful: redo the analysis
        record(state["project_id"], responder, "clarification_regenerate", {"round": round_no, "feedback": response.get("feedback", "")})
        return {"clarified": True, "clarification_round": round_no, "feedback": response.get("feedback", ""),
                "questions_iteration": state.get("iteration")}
    answered = [a for a in response.get("answers", []) if a.get("answer", "").strip()]
    if response.get("skip") or not answered:
        record(state["project_id"], responder, "clarification_skipped", {"round": round_no})
        return {"clarified": False, "clarification_round": round_no, "questions_iteration": state.get("iteration")}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for a in answered:
        grouped[a["target_role"]].append({"category": "clarification", "question": a["question"], "answer": a["answer"]})
    for role, answers in grouped.items():
        ingest(state["project_id"], "questionnaire", f"Clarification round {round_no} — {role_name(role)}",
               questionnaire_to_text(role_name(role), answers), role, actor=responder)
    record(state["project_id"], responder, "clarifications_answered",
           {"round": round_no, "answers": len(answered), "unanswered": len(questions) - len(answered), "roles": list(grouped)})
    return {"clarified": True, "clarification_round": round_no, "questions_iteration": state.get("iteration")}


# ---------- Baseline approval ----------

def required_baseline_approvers(state: ProjectState) -> list[str]:
    """Route the baseline to the roles accountable for what it contains, and to every role owning a decision."""
    active = [r for r in state.get("requirements", []) if r.get("status") not in ("rejected", "suggested")]
    roles = [get_settings().baseline_owner_role]
    if any("regulatory" in r["categories"] for r in active) or any(r.get("escalated") for r in active) or \
            interpretations(state):
        roles.append("compliance_legal")
    if any(f["severity"] == "high" for f in state.get("security_findings", [])) or \
            any(rk["type"] == "security" and rk["level"] == "high" for rk in state.get("risks", [])):
        roles.append("infosec")
    if any(r["priority"] == "must" and {"integration", "performance", "availability"} & set(r["categories"]) for r in active):
        roles.append("architect_developer")
    roles += [i["owner"] for i in decision_items(state).values()]
    return list(dict.fromkeys(roles))


def pending_baseline_approvers(state: ProjectState) -> list[str]:
    approved = {a["role"] for a in state.get("baseline_approvals", []) if a["decision"] == "approve"}
    return [r for r in required_baseline_approvers(state) if r not in approved]


def apply_edits(requirements: list[dict], edits: list[dict], by: str = "", role: str = "") -> list[dict]:
    by_id = {e["id"]: e for e in edits}
    out = []
    for r in requirements:
        e = by_id.get(r["id"])
        decision = {"by": by, "role": role, "at": _now()}
        if e is None:
            out.append(r)
        elif e["action"] == "accept":
            out.append(r | {"status": "accepted", "decision": decision | {"action": "accept"}})
        elif e["action"] == "reject":
            out.append(r | {"status": "rejected", "decision": decision | {"action": "reject"}})
        elif e["action"] == "modify" and e.get("statement"):
            out.append(r | {"status": "modified", "statement": e["statement"], "decision": decision | {"action": "modify"},
                            "original_statement": r.get("original_statement", r["statement"])})
        else:
            out.append(r)
    return out


def apply_interpretations(state: ProjectState, decisions: list[dict], by: str) -> tuple[dict, list[dict]]:
    """Record compliance & legal decisions on regulatory interpretations (accept / reject / modify)."""
    comp = state.get("compliance", {})
    by_id = {d["id"]: d for d in decisions}
    now = _now()
    mappings = []
    for m in comp.get("mappings", []):
        d = by_id.get(m.get("id"))
        if d is None:
            mappings.append(m)
            continue
        legal = {"action": d["action"], "by": by, "role": "compliance_legal", "at": now, "note": d.get("note", "")}
        m = m | {"legal_decision": legal}
        if d["action"] == "modify":
            m = m | {"original": {"regulation": m["regulation"], "obligation": m["obligation"]},
                     "regulation": d.get("regulation") or m["regulation"], "obligation": d.get("obligation") or m["obligation"]}
        if d["action"] in ("accept", "modify"):
            m = m | {"legal_approval": {"by": by, "at": now}}
        mappings.append(m)
    # Applicable regulations follow the human decisions: rejected interpretations no longer apply.
    regs: dict[str, set] = defaultdict(set)
    for m in mappings:
        if (m.get("legal_decision") or {}).get("action") != "reject":
            regs[m["req_id"]].add(m["regulation"])
    reqs = [r | {"applicable_regulations": sorted(regs.get(r["id"], set()))} for r in state["requirements"]]
    return comp | {"mappings": mappings}, reqs


def baseline_approval(state: ProjectState) -> ProjectState:
    items = decision_items(state)
    decision = interrupt({
        "gate": "baseline",
        "required_approvers": required_baseline_approvers(state),
        "pending_approvers": pending_baseline_approvers(state),
        "approvals": state.get("baseline_approvals", []),
        "requirements": state["requirements"],
        "decision_items": items,
        "escalated": [i for i, it in items.items() if not it["decided"]],
        "interpretations": interpretations(state),
        "issues": state.get("issues", []),
        "quality": state.get("quality", {}),
        "conflicts": state.get("conflicts", []),
        "clarifications": state.get("clarifications", []),
        "compliance": state.get("compliance", {}),
        "security_findings": state.get("security_findings", []),
        "risks": state.get("risks", []),
        "returned": state.get("returned", []),
        "quality_findings": state.get("quality_findings", []),
    })
    edits = decision.get("edits", [])
    legal = decision.get("interpretations", [])
    entry = {"role": decision["reviewer_role"], "reviewer": decision["reviewer"], "decision": decision["decision"],
             "feedback": decision.get("feedback", ""), "edits": len(edits), "interpretations": len(legal), "at": _now()}
    approvals = [*state.get("baseline_approvals", []), entry]
    record(state["project_id"], decision["reviewer"], f"baseline_{decision['decision']}",
           {"role": decision["reviewer_role"], "feedback": entry["feedback"], "edits": edits,
            "owned_decisions": [e["id"] for e in edits if items.get(e["id"], {}).get("owner") == decision["reviewer_role"]]})
    if decision["decision"] == "regenerate":
        return {"baseline_approvals": approvals, "feedback": entry["feedback"]}
    reqs = apply_edits(state["requirements"], edits, decision["reviewer"], decision["reviewer_role"])
    update: ProjectState = {"baseline_approvals": approvals, "requirements": reqs}
    if legal:
        # Step 11 + 16: the agent only proposes; the legal determination is this human decision, per interpretation.
        update["compliance"], update["requirements"] = apply_interpretations(state | {"requirements": reqs}, legal, decision["reviewer"])
        record(state["project_id"], decision["reviewer"], "legal_interpretations_decided",
               {d["action"]: sum(x["action"] == d["action"] for x in legal) for d in legal} | {"ids": [d["id"] for d in legal]})
    return update


# ---------- SDLC approval ----------

def pending_sdlc_approvers(state: ProjectState) -> list[str]:
    approved = {a["role"] for a in state.get("sdlc_approvals", []) if a["decision"] == "approve"}
    return [r for r in get_settings().sdlc_approvers if r not in approved]


def sdlc_approval(state: ProjectState) -> ProjectState:
    decision = interrupt({
        "gate": "sdlc",
        "required_approvers": get_settings().sdlc_approvers,
        "pending_approvers": pending_sdlc_approvers(state),
        "approvals": state.get("sdlc_approvals", []),
        "recommendations": state["sdlc_recommendations"],
        "factors": state["factors"],
        "rules_fired": state.get("sdlc_rules_fired", []),
        "explanation": state.get("sdlc_explanation", {}),
        "selected_model": state.get("sdlc_decision", {}).get("model"),
        "characteristics": state.get("sdlc_characteristics", []),
        "rules_version": state.get("sdlc_rules_version"),
    })
    top = state["sdlc_recommendations"][0]["model"]
    entry = {"role": decision["reviewer_role"], "reviewer": decision["reviewer"], "decision": decision["decision"],
             "feedback": decision.get("feedback", ""), "selected_model": decision.get("selected_model"), "at": _now(),
             "override": bool(decision.get("selected_model")) and decision.get("selected_model") != top}
    approvals = [*state.get("sdlc_approvals", []), entry]
    answers = {k: v for k, v in (decision.get("characteristic_answers") or {}).items()}
    record(state["project_id"], decision["reviewer"], f"sdlc_{decision['decision']}",
           {"role": decision["reviewer_role"], "selected_model": entry["selected_model"], "feedback": entry["feedback"],
            "override_of_recommendation": entry["override"], "characteristic_answers": answers})
    if decision["decision"] == "regenerate":
        # Human answers to the selection questions override derived and LLM answers in the re-ranking;
        # "unknown" withdraws an earlier human answer.
        human = {**state.get("sdlc_characteristic_answers", {}), **answers}
        human = {k: v for k, v in human.items() if v in ("yes", "no")}
        return {"sdlc_approvals": approvals, "feedback": entry["feedback"], "sdlc_characteristic_answers": human}
    model = entry["selected_model"] or state.get("sdlc_decision", {}).get("model") or top
    return {"sdlc_approvals": approvals, "sdlc_decision": {"model": model}}


# ---------- Workflow approval (step 15 output) ----------

def pending_workflow_approvers(state: ProjectState) -> list[str]:
    approved = {a["role"] for a in state.get("workflow_approvals", []) if a["decision"] == "approve"}
    return [r for r in get_settings().workflow_approvers if r not in approved]


def workflow_approval(state: ProjectState) -> ProjectState:
    from app.agents.workflow import apply_workflow_edits

    decision = interrupt({
        "gate": "workflow",
        "required_approvers": get_settings().workflow_approvers,
        "pending_approvers": pending_workflow_approvers(state),
        "approvals": state.get("workflow_approvals", []),
        "workflow": {k: v for k, v in state["sdlc_workflow"].items() if k != "generated"},
    })
    edits, schedule = decision.get("edits", []), decision.get("schedule", {})
    entry = {"role": decision["reviewer_role"], "reviewer": decision["reviewer"], "decision": decision["decision"],
             "feedback": decision.get("feedback", ""), "edits": len(edits), "schedule": schedule, "at": _now()}
    approvals = [*state.get("workflow_approvals", []), entry]
    record(state["project_id"], decision["reviewer"], f"workflow_{decision['decision']}",
           {"role": decision["reviewer_role"], "feedback": entry["feedback"], "edits": edits, "schedule": schedule})
    if decision["decision"] == "regenerate":
        return {"workflow_approvals": approvals, "feedback": entry["feedback"]}
    update: ProjectState = {"workflow_approvals": approvals}
    if edits or schedule:
        workflow, applied = apply_workflow_edits(state, edits, schedule)
        update["sdlc_workflow"] = workflow
        record(state["project_id"], decision["reviewer"], "workflow_modified",
               {"edits": len(applied), "schedule": schedule,
                "controls_reinstated": [c["control"] for c in workflow["controls_added_by_rules"]
                                        if c not in state["sdlc_workflow"].get("controls_added_by_rules", [])]})
    return update


# ---------- The two coordinator gates ----------

def asks_questions(state: ProjectState) -> bool:
    """Blocking questions are put to stakeholders once per analysis pass, for at most max_clarification_rounds."""
    blocking = any(q["severity"] == "blocking" for q in state.get("clarifications", []))
    return blocking and state.get("clarification_round", 0) < get_settings().max_clarification_rounds         and state.get("questions_iteration") != state.get("iteration")


def requirements_gate(state: ProjectState) -> ProjectState:
    """Approve requirements: answer the blocking questions first (if any), then sign off the baseline."""
    if asks_questions(state):
        return clarification_gate(state) | {"gate_step": "questions"}
    return baseline_approval(state) | {"gate_step": "signoff"}


def plan_gate(state: ProjectState) -> ProjectState:
    """Approve plan: the SDLC model first, then the workflow built for it."""
    if pending_sdlc_approvers(state):
        return sdlc_approval(state)
    return workflow_approval(state)
