"""Step 15 (workflow per SDLC model) and step 16 (human-in-the-loop rules): deterministic parts.

The full gate sequence, change requests and readiness reviews run through the API in tests/test_flow.py.
"""

import pytest

from app.hitl.controls import CONTROL_POINTS, decision_items, undecided
from app.rules.sdlc import _file_catalog
from app.rules.workflow import build_schedule, gantt, normalise_roles, project_start, schedule_params, timing_label

CAT = _file_catalog()
MODELS = {m["id"]: m for m in CAT["models"]}


def schedule(model_id: str, weeks: float = 1.0, proposed: dict | None = None):
    m = MODELS[model_id]
    phases = [p | {"duration_weeks": weeks} for p in m["phases"]]
    params = schedule_params(proposed or {}, m["execution"])
    return phases, params, build_schedule(phases, m["execution"]["structure"], params)


def test_every_model_has_an_execution_profile():
    kinds_needed = {"design", "implementation", "release"}
    for m in CAT["models"]:
        ex = m["execution"]
        assert ex["structure"] in ("sequential", "v_paired", "iterative", "cyclic", "continuous", "hybrid")
        assert set(ex["components"]) == {"activities", "security", "testing", "compliance", "approvals", "traceability"}
        kinds = {k for p in m["phases"] for k in p["kinds"]}
        assert kinds_needed <= kinds | {"design"} and ({"testing", "validation"} & kinds), m["id"]
        assert all(p["recurrence"] in ("once", "per_iteration", "per_release", "per_cycle", "continuous") for p in m["phases"])


def test_sequential_and_v_model_timelines():
    phases, params, s = schedule("waterfall", 2)
    occ = s["occurrences"]
    assert [occ[p["name"]][0]["start"] for p in phases[:5]] == [0, 2, 4, 6, 8] and s["total_weeks"] == 12
    assert timing_label(phases[0], occ["Requirements"], params) == "Weeks 1–2"
    v = MODELS["v_model"]
    assert {p["name"]: p.get("pairs_with") for p in v["phases"] if p.get("pairs_with")}["System design"] == "System testing"


def test_iterative_timeline_with_releases():
    phases, params, s = schedule("agile", 1, {"iterations": 4, "iteration_length_weeks": 2, "iterations_per_release": 2})
    occ = s["occurrences"]
    assert len(occ["Sprint execution"]) == 4 and len(occ["Release"]) == 2
    assert occ["Release"][0]["start"] == 4  # after sprint 2
    assert timing_label(phases[2], occ["Sprint execution"], params).startswith("Every iteration (4 × 2 weeks)")
    _, params, _ = schedule("agile", 1, {"iterations": 99, "iteration_length_weeks": 0})
    assert params["iterations"] == 20 and params["iteration_length_weeks"] == 1  # clamped to sane bounds


def test_cyclic_continuous_and_hybrid_timelines():
    _, _, s = schedule("spiral", 2, {"cycles": 2})
    assert [o["label"] for o in s["occurrences"]["Risk analysis and prototyping"]] == ["Cycle 1", "Cycle 2"]
    _, _, s = schedule("devsecops", 1, {"iterations": 3, "iteration_length_weeks": 2, "iterations_per_release": 1})
    occ = s["occurrences"]
    assert occ["Test"][0]["label"] == "Continuous" and occ["Test"][0]["end"] == s["total_weeks"]
    assert occ["Operate"][0]["start"] == occ["Release"][0]["start"]  # operation begins with the first release
    phases, params, s = schedule("agile_v_hybrid", 2, {"iterations": 4, "iterations_per_release": 2})
    occ = s["occurrences"]
    assert len(occ["Regulatory requirements baseline"]) == 1 and len(occ["Controlled release"]) == 2
    chart = gantt("Agile–V-Model hybrid", phases, occ, project_start())
    assert chart.startswith("gantt") and "section Controlled release" in chart and ":" not in chart.split("title")[1].split("\n")[0]


def test_role_normalisation():
    assert normalise_roles(["Project Manager", "Information-security teams", "Compliance officer", "QA engineer"]) == \
        ["project_manager", "infosec", "compliance_legal", "QA engineer"]


def _req(i, cats, prio="should", **kw):
    return {"id": i, "statement": "s", "categories": cats, "priority": prio, "origin": "extracted", "status": "proposed",
            "stakeholder_role": kw.pop("role", "customer")} | kw


def test_decision_ownership():
    state = {"requirements": [
        _req("FR-1", ["security"], risk_level="high"),
        _req("NFR-1", ["performance"], prio="must"),
        _req("FR-2", ["functional"], role="customer"), _req("FR-3", ["functional"], role="risk_management"),
        _req("FR-4", ["regulatory"], escalated=True, escalation_reasons=["unsupported"], grounding_support="unsupported"),
        _req("FR-5", ["usability"], escalated=True, escalation_reasons=["low confidence"]),
        _req("SUG-SEC-001", ["security"], origin="security_privacy_agent", status="suggested", risk_level="high"),
        _req("SUG-SEC-002", ["security"], origin="security_privacy_agent", status="suggested", risk_level="low"),
        _req("SUG-CMP-001", ["regulatory"], origin="compliance_agent", status="suggested"),
        _req("FR-6", ["functional"], status="accepted", risk_level="high"),
    ], "conflicts": [{"kind": "conflict", "req_ids": ["FR-2", "FR-3"]}, {"kind": "duplicate", "req_ids": ["FR-1", "FR-6"]}]}
    items = decision_items(state)
    owners = {i: it["owner"] for i, it in items.items()}
    assert owners == {"FR-1": "infosec", "NFR-1": "architect_developer", "FR-2": "product_owner", "FR-3": "product_owner",
                      "FR-4": "compliance_legal", "FR-5": "product_owner", "SUG-SEC-001": "infosec",
                      "SUG-CMP-001": "compliance_legal"}
    assert items["FR-2"]["controls"] == ["stakeholder_conflicts"] and "SUG-SEC-002" not in items
    assert undecided(items, "infosec", [{"id": "FR-1"}]) == ["SUG-SEC-001"]
    assert len(CONTROL_POINTS) == 9


@pytest.mark.parametrize("control", ["baseline", "regulatory_interpretations", "high_risk_security", "stakeholder_conflicts",
                                     "architecture_critical", "sdlc_selection", "requirement_changes", "production_readiness"])
def test_all_eight_step16_controls_are_registered(control):
    assert control in {c["id"] for c in CONTROL_POINTS}
