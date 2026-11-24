"""Deterministic parts of the agent standards (steps 8-13); the full graph is covered in test_flow.py."""

from app.agents.clarification import _fallback_questions
from app.agents.documentation import assumptions_dependencies, process_workflows
from app.agents.sdlc import measured_factors
from app.agents.standards import (ARTEFACTS, QUALITY_CHECKS, REQUIREMENT_FIELDS, SDLC_FACTORS, quote_in_source,
                                  standard_record)
from app.catalog.loader import DATA_DIR
from app.rules.sdlc import rank_sdlc_models
from app.schemas import ProjectFactors

import yaml


def test_standard_lists_match_problem_statement():
    assert len(REQUIREMENT_FIELDS) == 13 and len(QUALITY_CHECKS) == 10 and len(ARTEFACTS) == 11 and len(SDLC_FACTORS) == 13
    factor_ids = {k for k, _ in SDLC_FACTORS}
    assert factor_ids <= set(ProjectFactors.model_fields)
    catalog = yaml.safe_load((DATA_DIR / "sdlc_models.yaml").read_text(encoding="utf-8"))
    assert factor_ids <= {f["id"] for f in catalog["factors"]}
    assert all(factor_ids <= set(m["ideal_profile"]) for m in catalog["models"])


def test_standard_record_and_quote_check():
    r = {"id": "FR-LOAN-001", "statement": "s", "categories": ["security"], "priority": "must", "acceptance_criteria": [],
         "confidence": 0.8, "stakeholder_role": "customer", "depends_on": ["FR-LOAN-002"], "dependencies": ["Bureau API"],
         "source_quote": "extra verification for big loans", "status": "accepted"}
    rec = standard_record(r)
    assert [k for k, _ in REQUIREMENT_FIELDS] == [k for k in rec if k != "trace"]
    assert rec["dependencies"] == ["FR-LOAN-002", "Bureau API"] and rec["approval_status"] == "accepted"
    assert rec["risk_level"] == "low" and rec["trace"]["source_quote"]
    source = "I want extra verification for big loans, and it should be fast."
    assert quote_in_source("Extra verification for big loans!", source) == "exact"
    assert quote_in_source("verification for the big loans", source) == "paraphrased"
    assert quote_in_source("approve every loan instantly", source) == "not_found"


def test_every_returned_requirement_gets_a_question():
    returned = [
        {"req_id": "FR-1", "stakeholder_role": "customer", "categories": ["functional"], "blocking": False,
         "checks": [{"check": "ambiguity", "message": "Vague term 'fast'", "severity": "medium"}]},
        {"req_id": "FR-2", "stakeholder_role": None, "categories": ["security"], "blocking": True,
         "checks": [{"check": "ambiguity", "message": "x", "severity": "medium"},
                    {"check": "infeasibility", "message": "100% uptime", "severity": "high"}]},
    ]
    qs = _fallback_questions(returned, covered={"FR-1"})
    assert [q["related_req_ids"] for q in qs] == [["FR-2"]]  # FR-1 already has an LLM question
    assert qs[0]["severity"] == "blocking" and qs[0]["target_role"] == "architect_developer"  # infeasibility owner
    assert "may not be achievable" in qs[0]["question"]


def test_measured_factors_and_ranking_with_missing_factors():
    small = measured_factors({"requirements": 8, "integration_requirements": 0, "stakeholder_coverage": 1.0,
                              "open_blocking_questions": 0})
    assert small == {"system_size": 1, "stakeholder_availability": 5}
    big = measured_factors({"requirements": 60, "integration_requirements": 7, "stakeholder_coverage": 0.25,
                            "open_blocking_questions": 2})
    assert big == {"system_size": 5, "stakeholder_availability": 1}
    old = {k: 3 for k in ("requirement_stability", "regulatory_criticality", "security_risk", "complexity",
                          "change_frequency", "continuous_delivery_need", "formal_verification_need", "technical_uncertainty")}
    assert len(rank_sdlc_models(old)) == 10  # factors added later default to the midpoint


def test_process_workflow_and_register():
    uc = {"id": "UC-01", "title": "Apply for loan", "primary_actor": "Borrower", "main_flow": ["Enter amount", "Pass OTP"],
          "alternative_flows": ["Save draft"], "exception_flows": ["OTP fails"], "postconditions": ["Application stored"],
          "requirement_ids": ["FR-1"]}
    req = {"id": "FR-1", "statement": "s", "assumptions": ["Mobile only"], "depends_on": [], "dependencies": ["SMS gateway"]}
    flow = process_workflows([uc], {"FR-1": req})[0]
    assert flow["id"] == "PF-01" and "M2 --> E" in flow["mermaid"] and "Exception: OTP fails" in flow["mermaid"]
    assert flow["trace"][0]["req_id"] == "FR-1"
    reg = assumptions_dependencies([req])
    assert [(x["id"], x["text"]) for x in reg] == [("ASM-01", "Mobile only"), ("DEP-01", "SMS gateway")]
