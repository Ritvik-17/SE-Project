"""The simplified seven-agent flow: routing, the two coordinator gates, classification IDs and planning reuse."""

from app.agents.approval import asks_questions
from app.agents.classification import _renumber
from app.agents.coordinator import after_plan, after_requirements
from app.agents.planning import sdlc_settled
from app.agents.review import own_findings
from app.config import get_settings
from app.graph.builder import build_analysis_graph

BLOCKING = [{"severity": "blocking", "question": "q", "target_role": "risk_management", "related_req_ids": []}]


def test_seven_agents_own_every_node():
    owners = {"coordinator": {"intake", "consolidate", "assess", "requirements_gate", "plan_gate"},
              "extraction": {"extraction"}, "classification": {"classification"}, "review": {"review"},
              "compliance_security": {"compliance_security"}, "planning": {"planning"},
              "documentation": {"freeze_baseline", "documentation"}}
    nodes = set(build_analysis_graph().get_graph().nodes) - {"__start__", "__end__"}
    assert len(owners) == 7 and nodes == set().union(*owners.values())


def test_blocking_questions_asked_once_per_pass():
    state = {"clarifications": BLOCKING, "clarification_round": 0, "iteration": 1}
    assert asks_questions(state)
    assert not asks_questions(state | {"questions_iteration": 1})  # skipped this pass → straight to sign-off
    assert asks_questions(state | {"questions_iteration": 1, "iteration": 2})  # new pass after answers
    assert not asks_questions(state | {"clarification_round": get_settings().max_clarification_rounds})
    assert not asks_questions(state | {"clarifications": [BLOCKING[0] | {"severity": "non_blocking"}]})


def test_requirements_gate_routing():
    assert after_requirements({"gate_step": "questions", "clarified": True}) == "intake"
    assert after_requirements({"gate_step": "questions", "clarified": False}) == "requirements_gate"
    assert after_requirements({"gate_step": "signoff", "baseline_approvals": [{"decision": "regenerate"}]}) == "intake"
    pending = {"gate_step": "signoff", "requirements": [], "baseline_approvals": []}
    assert after_requirements(pending) == "requirements_gate"
    owner = get_settings().baseline_owner_role
    assert after_requirements(pending | {"baseline_approvals": [{"role": owner, "decision": "approve"}]}) == "freeze_baseline"


def test_plan_gate_routing():
    s = get_settings()
    sdlc_done = [{"role": r, "decision": "approve"} for r in s.sdlc_approvers]
    wf_done = [{"role": r, "decision": "approve"} for r in s.workflow_approvers]
    base = {"sdlc_decision": {"model": "V-Model"}, "sdlc_workflow": {"model": "V-Model"}}
    assert after_plan(base | {"sdlc_approvals": []}) == "plan_gate"                         # model not yet approved
    assert after_plan(base | {"sdlc_approvals": [{"role": "x", "decision": "regenerate"}]}) == "planning"
    assert after_plan(base | {"sdlc_approvals": sdlc_done, "sdlc_workflow": {"model": "Waterfall"}}) == "planning"
    assert after_plan(base | {"sdlc_approvals": sdlc_done, "workflow_approvals": []}) == "plan_gate"
    assert after_plan(base | {"sdlc_approvals": sdlc_done, "workflow_approvals": [{"role": "x", "decision": "regenerate"}]}) == "planning"
    assert after_plan(base | {"sdlc_approvals": sdlc_done, "workflow_approvals": wf_done}) == "documentation"


def test_planning_reuses_an_approved_model():
    s = get_settings()
    assert not sdlc_settled({"sdlc_approvals": []})
    assert not sdlc_settled({"sdlc_approvals": [{"role": s.sdlc_approvers[0], "decision": "regenerate"}]})
    assert sdlc_settled({"sdlc_approvals": [{"role": r, "decision": "approve"} for r in s.sdlc_approvers]})


def test_classification_sets_the_id_prefix():
    reqs = [{"id": "FR-LOAN-001", "type": "non_functional", "depends_on": []},
            {"id": "FR-LOAN-002", "type": "functional", "depends_on": ["FR-LOAN-001", "FR-OTHER"]},
            {"id": "NFR-LOAN-001", "type": "functional", "depends_on": []}]
    out, renamed = _renumber(reqs, "loan_processing")
    assert [r["id"] for r in out] == ["NFR-LOAN-001", "FR-LOAN-001", "FR-LOAN-002"] and renamed == 3
    assert out[1]["depends_on"] == ["NFR-LOAN-001", "FR-OTHER"]  # remapped; unknown references left alone


def test_review_turns_its_findings_into_questions_input():
    state = {"requirements": [
        {"id": "FR-1", "statement": "a", "categories": ["functional"], "stakeholder_role": "customer"},
        {"id": "FR-2", "statement": "b", "categories": ["business"], "stakeholder_role": "risk_management"}]}
    found = {"quality_findings": [{"req_id": "FR-1", "check": "ambiguity", "explanation": "vague"},
                                  {"req_id": "GHOST", "check": "ambiguity", "explanation": "x"}],
             "conflicts": [{"kind": "conflict", "req_ids": ["FR-1", "FR-2"], "description": "limits differ"}]}
    out = {i["req_id"]: i for i in own_findings(state, found)}
    assert set(out) == {"FR-1", "FR-2"}
    assert out["FR-2"]["blocking"] and out["FR-2"]["checks"][0]["check"] == "conflicting_stakeholder_expectations"
    assert {c["check"] for c in out["FR-1"]["checks"]} == {"ambiguity", "conflicting_stakeholder_expectations"}
