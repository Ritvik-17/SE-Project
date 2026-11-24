"""SDLC selection engine (step 14): course matrices, answer precedence, rules and rankings.

The scenarios check that the engine reproduces the guidance it was built from (problem-statement decision table,
CS305 course slides, research); see guide/sdlc_selection_research_and_rules.md.
"""

import pytest

from app.rules.sdlc import (_file_catalog, characteristic_questions, derive_answers, merge_answers, rank_sdlc_models,
                            rules_fired, suitability, yn)

CAT = _file_catalog()
NEUTRAL = {f["id"]: 3 for f in CAT["factors"]}


def top(factors: dict, human: dict | None = None, n: int = 1) -> list[str]:
    answers = merge_answers({}, derive_answers(factors, {}, CAT), human or {})
    return [r["model_id"] for r in rank_sdlc_models(factors, answers, CAT)[:n]]


def test_catalog_shape():
    ids = [m["id"] for m in CAT["models"]]
    assert ids == ["waterfall", "v_model", "prototype", "spiral", "rad", "incremental", "agile", "devsecops",
                   "agile_v_hybrid", "agile_devsecops_hybrid"]
    qs = characteristic_questions(CAT)
    assert len(qs) == 19 and {q["category"] for q in qs} == {"requirements", "project_team", "user_community",
                                                            "project_type_risk"}
    assert all(set(q["fits"]) == set(ids) and all(yn(v) for v in q["fits"].values()) for q in qs)
    assert all(r.get("source") for r in CAT["rules"]) and all(m.get("source") for m in CAT["models"])
    assert {r["id"][:2] for r in CAT["rules"]} >= {"PS", "C1", "R1"}


@pytest.mark.parametrize("qid, column", [
    # Spot checks against the course slides (Topic 2 part 4), one row per matrix
    ("req_well_known", {"waterfall": "yes", "v_model": "yes", "prototype": "no", "spiral": "no", "rad": "yes", "incremental": "no"}),
    ("team_new_to_technology", {"waterfall": "yes", "v_model": "yes", "prototype": "no", "spiral": "yes", "rad": "no", "incremental": "yes"}),
    ("users_limited", {"waterfall": "yes", "v_model": "yes", "prototype": "no", "spiral": "yes", "rad": "no", "incremental": "yes"}),
    ("funding_stable", {"waterfall": "yes", "v_model": "yes", "prototype": "yes", "spiral": "no", "rad": "yes", "incremental": "no"}),
])
def test_course_matrix_columns(qid, column):
    q = next(q for q in characteristic_questions(CAT) if q["id"] == qid)
    assert {m: yn(q["fits"][m]) for m in column} == column


def test_answer_precedence_and_derivation():
    factors = NEUTRAL | {"change_frequency": 5, "stakeholder_availability": 1}
    derived = derive_answers(factors, {"integration_requirements": 0}, CAT)
    assert derived["req_change_often"]["answer"] == "yes" and derived["users_limited"]["answer"] == "yes"
    assert derived["system_integration"]["answer"] == "no" and "req_well_known" not in derived  # 3 is inconclusive
    merged = merge_answers({"req_change_often": {"answer": "no"}, "long_life": {"answer": "yes", "reason": "core system"},
                            "funding_stable": {"answer": "unknown"}}, derived, {"users_limited": "no"})
    assert merged["req_change_often"]["source"] == "derived"  # measured data beats the LLM
    assert merged["users_limited"] == {"answer": "no", "source": "human", "reason": "answered at the SDLC gate"}
    assert merged["long_life"]["source"] == "llm" and merged["funding_stable"]["answer"] is None


def test_unknown_answers_do_not_count():
    with_none = rank_sdlc_models(NEUTRAL, {}, CAT)
    assert all(r["characteristics_fit"] is None for r in with_none)
    one = rank_sdlc_models(NEUTRAL, {"funding_stable": {"answer": "no"}}, CAT)
    by = {r["model_id"]: r for r in one}
    assert by["spiral"]["characteristics"]["project_type_risk"] == {"matched": 1, "answered": 1, "mismatched": []}
    assert by["waterfall"]["characteristics"]["project_type_risk"]["mismatched"] == ["funding_stable"]


def test_rules_use_answers_and_report_sources():
    fired = {r["rule"]: r for r in rules_fired(NEUTRAL | {"regulatory_criticality": 5, "change_frequency": 4}, {}, CAT)}
    assert {"PS4", "PS6a", "R6", "C3", "C5", "C7"} <= set(fired) and fired["C5"]["source"].startswith("COURSE")
    answers = {"team_new_to_domain": {"answer": "yes"}, "training_available": {"answer": "no"}}
    assert "R3" in {r["rule"] for r in rules_fired(NEUTRAL, answers, CAT)}
    assert "C6" in {r["rule"] for r in rules_fired(NEUTRAL | {"system_size": 4}, {}, CAT)}  # when_any


def test_suitability_is_monotonic_and_bounded():
    values = [suitability(x) for x in (-20, 0, 40, 70, 100, 120, 200)]
    assert values == sorted(values) and values[0] == 0 and values[-1] <= 100
    assert suitability(120) > suitability(100)  # strong candidates stay distinguishable


@pytest.mark.parametrize("name, factors, human, expected", [
    ("PS: stable requirements, extensive approvals",
     {"requirement_stability": 5, "change_frequency": 1, "technical_uncertainty": 1, "complexity": 2,
      "continuous_delivery_need": 1, "budget_schedule_constraint": 5, "testing_documentation_need": 4}, {}, "waterfall"),
    ("PS: strict verification and validation, legacy core",
     {"requirement_stability": 4, "regulatory_criticality": 4, "formal_verification_need": 5, "failure_consequence": 5,
      "testing_documentation_need": 5, "change_frequency": 2, "legacy_dependence": 5, "continuous_delivery_need": 1},
     {"enhancement_existing": "yes", "long_life": "yes"}, "v_model"),
    ("PS: high uncertainty or technical risk",
     {"requirement_stability": 2, "complexity": 5, "technical_uncertainty": 5, "system_size": 5, "security_risk": 4,
      "failure_consequence": 4, "budget_schedule_constraint": 2}, {"proof_of_concept": "yes", "funding_stable": "no"}, "spiral"),
    ("PS: frequently changing requirements",
     {"requirement_stability": 2, "regulatory_criticality": 2, "change_frequency": 5, "continuous_delivery_need": 4,
      "stakeholder_availability": 5, "failure_consequence": 2, "system_size": 2, "formal_verification_need": 2},
     {"users_involved_all_phases": "yes", "users_domain_experts": "yes"}, "agile"),
    ("PS: continuous secure deployment",
     {"security_risk": 5, "continuous_delivery_need": 5, "change_frequency": 4, "complexity": 4, "system_size": 4,
      "stakeholder_availability": 4, "legacy_dependence": 2, "regulatory_criticality": 3}, {"long_life": "yes"}, "devsecops"),
    ("PS: high regulation, evolving requirements",
     {"regulatory_criticality": 5, "change_frequency": 4, "formal_verification_need": 5, "failure_consequence": 5,
      "testing_documentation_need": 5, "security_risk": 4, "continuous_delivery_need": 3, "legacy_dependence": 4},
     {}, "agile_v_hybrid"),
    ("PS: high regulation, evolving, continuous delivery",
     {"regulatory_criticality": 5, "change_frequency": 4, "continuous_delivery_need": 5, "security_risk": 5,
      "formal_verification_need": 4, "stakeholder_availability": 4, "failure_consequence": 4}, {}, "agile_devsecops_hybrid"),
    ("COURSE: heavy user interaction, unclear requirements",
     {"requirement_stability": 1, "change_frequency": 4, "technical_uncertainty": 4, "stakeholder_availability": 5,
      "regulatory_criticality": 2, "formal_verification_need": 1, "system_size": 2},
     {"users_involved_all_phases": "yes", "need_demonstrate": "yes", "proof_of_concept": "yes"}, "prototype"),
    ("COURSE: modular system needed in 2-3 months",
     {"system_size": 1, "regulatory_criticality": 1, "stakeholder_availability": 5, "budget_schedule_constraint": 5,
      "formal_verification_need": 1, "testing_documentation_need": 1, "failure_consequence": 1, "complexity": 2},
     {"users_involved_all_phases": "yes", "need_demonstrate": "yes", "users_domain_experts": "yes", "long_life": "no"}, "rad"),
    ("COURSE: major requirements known, details evolve, large",
     {"requirement_stability": 3, "change_frequency": 3, "system_size": 4, "complexity": 4, "failure_consequence": 4},
     {"req_defined_early": "yes", "team_reassignment": "yes", "funding_stable": "no"}, "incremental"),
])
def test_engine_reproduces_the_guidance(name, factors, human, expected):
    assert top(NEUTRAL | factors, human)[0] == expected, name
