"""SDLC-selection agent (step 14). The project-specific workflow (step 15) is app/agents/workflow.py.

Hybrid decision (research and rule sources: guide/sdlc_selection_research_and_rules.md):
  1. inputs:  the thirteen project factors (step 13) and the answers to the course's 19 SDLC-selection questions
              (requirements, project team, user community, project type and risk). Answers come from a human at
              the SDLC gate, else from measured data, else from the LLM; unknown answers are left out.
  2. ranking: deterministic engine (app/rules/sdlc.py): TOPSIS + weighted fit over factors and characteristic
              categories, then decision rules from the problem statement, the course and published research.
  3. explanation: the LLM explains the ranking without being allowed to change it.
The project manager, architect, security team and compliance officer approve the final choice (SDLC_APPROVERS).

Standard (step 13): all thirteen decision factors (standards.SDLC_FACTORS) are derived. `factor_signals()` measures
what the project data can tell directly (requirement counts, integrations, legacy mentions, stakeholder coverage,
open questions, schedule and budget statements). System size and stakeholder availability are computed from those
signals rather than estimated; the LLM scores the rest with the signals in front of it. After approval, the selected model's
phases are tailored into a project-specific workflow; mandatory financial-sector controls are enforced by rules.
"""

import re

from app import llm
from app.agents.common import domain_name, format_requirements
from app.agents.standards import SDLC_FACTORS
from app.audit import record
from app.catalog.loader import get_catalog
from app.graph.state import ProjectState
from app.rules.sdlc import (characteristic_questions, derive_answers, load_sdlc_catalog_versioned,
                             merge_answers, rank_sdlc_models, rules_fired)
from app.schemas import CharacteristicAnswers, ProjectFactors, SdlcExplanation

FACTORS_PROMPT = """You are a software-process expert for financial institutions.
Score the SDLC decision factors (1-5) for this {domain} project from its approved requirement baseline,
risks and compliance profile. Justify the scores briefly.
{feedback}
Factors: {factor_names}.
- budget_schedule_constraint: 5 = fixed, tight deadline and budget; 1 = flexible.
- failure_consequence: 5 = financial loss, regulatory breach or customer harm at scale if the system fails.
- testing_documentation_need: 5 = extensive test evidence and documentation demanded (regulators, auditors).
- legacy_dependence: 5 = core functions depend on legacy / core-banking systems.

Measured project signals (use them; do not contradict them):
{signals}

Risks (top): {risks}
Compliance mappings needing legal review: {legal}

Requirements:
{requirements}"""

CHARACTERISTICS_PROMPT = """Answer these SDLC-selection questions for a {domain} project at a bank, using only the
project information below. Answer "unknown" when the information does not tell (team skills, staffing and funding
are often not in the requirements); never guess. Give the evidence for each answer in one line.

Questions:
{questions}

Project factors (1-5): {factors}
Measured signals: {signals}
Requirements:
{requirements}"""

EXPLAIN_PROMPT = """Explain an SDLC recommendation for a {domain} project to its approvers (project manager, architect,
security team, compliance officer). The ranking below was computed by a deterministic engine: TOPSIS and weighted fit
over the project factors and the project characteristics (course selection matrices), then decision rules from the
problem statement, the course and published research. Do NOT change or dispute the order; explain it using the
factors, the characteristic answers, the rules that fired (cite their sources) and the requirements.

Project factors (1-5): {factors}
Factor rationale: {rationale}
Project characteristics: {characteristics}
Rules fired: {rules}
Ranking:
{ranking}

Key requirements:
{requirements}"""

def baseline(state: ProjectState) -> list[dict]:
    return [r for r in state["requirements"] if r.get("status") not in ("rejected", "suggested")]


LEGACY = re.compile(r"\b(legacy|mainframe|core[- ]banking|cbs|existing system|batch file|cobol|as400|flat file)\b", re.I)
SCHEDULE = re.compile(r"\b(deadline|go[- ]live|launch|budget|cost|by (q[1-4]|january|february|march|april|may|june|july|"
                      r"august|september|october|november|december|\d{4})|within \d+ (weeks|months))\b", re.I)


def factor_signals(state: ProjectState) -> dict:
    """Facts measured from the project, used to derive (or anchor) the step-13 factors."""
    reqs = baseline(state)
    domain = get_catalog().domain(state["domain"])
    text = lambda r: " ".join([r["statement"], *r.get("dependencies", []), *r.get("assumptions", [])])  # noqa: E731
    roles = {s["stakeholder_role"] for s in state.get("sources", []) if s["stakeholder_role"]}
    required = domain.required_roles if domain else []
    open_blocking = [q for q in state.get("clarifications", []) if q["severity"] == "blocking"]
    n = len(reqs) or 1
    return {
        "requirements": len(reqs),
        "integration_requirements": sum("integration" in r["categories"] for r in reqs),
        "legacy_mentions": sum(bool(LEGACY.search(text(r))) for r in reqs),
        "dependencies": sum(len(r.get("depends_on", [])) + len(r.get("dependencies", [])) for r in reqs),
        "regulatory_or_audit_share": round(sum(bool({"regulatory", "audit"} & set(r["categories"])) for r in reqs) / n, 2),
        "must_share": round(sum(r["priority"] == "must" for r in reqs) / n, 2),
        "stakeholder_coverage": round(len(roles & set(required)) / len(required), 2) if required else 1.0,
        "stakeholder_roles": sorted(roles),
        "open_blocking_questions": len(open_blocking),
        "clarification_rounds": state.get("clarification_round", 0),
        "schedule_budget_statements": [r["statement"] for r in reqs if SCHEDULE.search(text(r))][:5],
        "high_risks": sum(rk["level"] == "high" for rk in state.get("risks", [])),
        "availability_requirements": sum("availability" in r["categories"] for r in reqs),
    }


def measured_factors(signals: dict) -> dict:
    """Factors computed from data rather than estimated by the LLM."""
    size = next(i for i, limit in enumerate((10, 25, 50, 100, 10**9), 1) if signals["requirements"] <= limit)
    size = min(5, size + (signals["integration_requirements"] >= 5))
    availability = 1 + round(4 * signals["stakeholder_coverage"]) - (signals["open_blocking_questions"] > 0)
    return {"system_size": size, "stakeholder_availability": max(1, min(5, availability))}


def sdlc_selection(state: ProjectState) -> ProjectState:
    feedback = f"\nApprover feedback on the previous recommendation (address it):\n{state['feedback']}\n" \
        if state.get("sdlc_approvals") and state.get("feedback") else ""
    risks = "; ".join(f"{r['title']} ({r['level']})" for r in state.get("risks", [])[:6]) or "none"
    legal = sum(m["needs_legal_review"] for m in state.get("compliance", {}).get("mappings", []))
    reqs = format_requirements(baseline(state))
    signals = factor_signals(state)
    factors = llm.structured(ProjectFactors, FACTORS_PROMPT.format(
        domain=domain_name(state["domain"]), feedback=feedback, risks=risks, legal=legal, requirements=reqs,
        factor_names=", ".join(f"{k} ({name})" for k, name in SDLC_FACTORS), signals=signals))
    values = factors.model_dump()
    for k, v in values.items():
        if isinstance(v, int):
            values[k] = max(1, min(5, v))
    measured = measured_factors(signals)
    values |= measured
    values["factor_sources"] = {k: "measured" if k in measured else "llm" for k, _ in SDLC_FACTORS}

    # Course characteristic questions: human > derived from measured data > LLM
    cat, version = load_sdlc_catalog_versioned()
    human = state.get("sdlc_characteristic_answers", {})
    derived = derive_answers(values, signals, cat)
    ask = [q for q in characteristic_questions(cat) if q["id"] not in derived and q["id"] not in human]
    llm_answers: dict[str, dict] = {}
    if ask:
        result = llm.structured(CharacteristicAnswers, CHARACTERISTICS_PROMPT.format(
            domain=domain_name(state["domain"]), questions="\n".join(f"- {q['id']}: {q['text']}" for q in ask),
            factors={k: v for k, v in values.items() if isinstance(v, int)}, signals=signals, requirements=reqs))
        asked = {q["id"] for q in ask}
        llm_answers = {a.id: a.model_dump() for a in result.answers if a.id in asked}
    answers = merge_answers(llm_answers, derived, human)
    characteristics = [{"id": q["id"], "text": q["text"], "category": q["category"], "category_name": q["category_name"]}
                       | answers.get(q["id"], {"answer": None, "source": "unknown", "reason": ""})
                       for q in characteristic_questions(cat)]
    ranked = rank_sdlc_models(values, answers, cat)
    fired = rules_fired(values, answers, cat)

    ranking_text = "\n".join(
        f"{i}. {r['model']} — {r['score']}% (TOPSIS {r['topsis']}, fit {r['fit']}, characteristics matched "
        f"{r['characteristics_fit'] if r['characteristics_fit'] is not None else 'n/a'}%, rules "
        f"{', '.join(f'{a['rule']} {a['points']:+d}' for a in r['rule_adjustments']) or 'none'}); "
        f"drivers: {', '.join(r['key_drivers'])}; concerns: {', '.join(r['concerns']) or 'none'}"
        for i, r in enumerate(ranked, 1))
    explanation = llm.structured(SdlcExplanation, EXPLAIN_PROMPT.format(
        domain=domain_name(state["domain"]),
        factors={k: v for k, v in values.items() if isinstance(v, int)}, rationale=values["rationale"],
        rules="; ".join(f"{r['rule']} ({r['source']}): {r['reason']}" for r in fired) or "none", ranking=ranking_text,
        characteristics="; ".join(f"{c['id']}={c['answer'] or 'unknown'} ({c['source']})" for c in characteristics),
        requirements=reqs))
    record(state["project_id"], "sdlc_selection_agent", "recommended_sdlc",
           {"factors": values, "ranking": [(r["model"], r["score"]) for r in ranked], "rules_fired": [r["rule"] for r in fired],
            "characteristics": {c["id"]: [c["answer"], c["source"]] for c in characteristics}, "rules_version": version})
    return {"factors": values, "factor_signals": signals, "sdlc_recommendations": ranked, "sdlc_rules_fired": fired,
            "sdlc_rules_version": version, "sdlc_characteristics": characteristics,
            "sdlc_explanation": explanation.model_dump(), "sdlc_approvals": [],
            "sdlc_decision": {"model": ranked[0]["model"]}}
