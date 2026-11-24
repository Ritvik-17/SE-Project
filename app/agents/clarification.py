"""Clarification agent: detects missing, vague or undefined information and routes questions to the right role.

Runs after validation (step 10): besides domain-level gaps, it receives every requirement that failed a quality
check (`returned`) and must produce at least one question for each. Any returned requirement the LLM does not
cover gets a deterministic question, so no failure is silently dropped. Questions for failures in BLOCKING_CHECKS
are blocking: the clarification gate pauses for them before the baseline can be approved.
"""

from app import llm
from app.agents.common import domain_name, format_requirements, roles_reference
from app.agents.standards import BLOCKING_CHECKS, CHECK_OWNER, QUALITY_CHECKS
from app.audit import record
from app.catalog.loader import get_catalog
from app.graph.state import ProjectState
from app.kb.lookup import terms_in
from app.kb.retrieval import evidence_block, search
from app.schemas import ClarificationResult

PROMPT = """You are the clarification agent for a {domain} project.
Identify information that is missing, ambiguous or undefined in the requirements below, for example:
undefined thresholds/limits, unquantified quality terms ("fast", "secure"), unclear actors, missing exception
handling, missing data-retention periods, undefined terminology, or topics the domain normally needs but nobody covered.
Mandatory topics for this domain: {mandatory}.

The validation agent RETURNED these requirements because they failed quality checks. Ask at least one question
for each, listing its ID in related_req_ids, that would let it pass (e.g. ask for the figure behind a vague term, the
missing actor, which of two conflicting stakeholder expectations is right, or the source of an unsupported claim):
{returned}

For each question, assign the stakeholder role best placed to answer:
{roles}

Mark a question "blocking" only if a requirement cannot be baselined or tested without the answer.
Do not ask questions already answered by the requirements, and do not ask what a defined term means.
Ask what an UNDEFINED acronym or term means. Use previously approved projects in <evidence> to spot topics this
project has not covered yet. At most {limit} questions, most important first.

Defined terms (from the glossary): {defined}
Undefined acronyms found in the requirements: {undefined}

<evidence>
{history}
</evidence>

Requirements:
{requirements}"""

FALLBACK = {
    "ambiguity": "{id} uses vague wording ({detail}). What specific, measurable value or rule is meant?",
    "incompleteness": "{id} is incomplete ({detail}). Who performs it, when, under what conditions and with what data?",
    "inconsistency": "{id} is inconsistent ({detail}). Which statement is correct?",
    "duplication": "{id} overlaps another requirement ({detail}). Should they be merged, and with what wording?",
    "infeasibility": "{id} may not be achievable as stated ({detail}). What target is realistic and acceptable?",
    "lack_of_testability": "{id} cannot be tested as written. How will we verify it is met (measurable acceptance criteria)?",
    "missing_source": "{id} has no verifiable source statement. Who asked for this requirement, and where is it stated?",
    "undefined_terminology": "{id} uses an undefined term ({detail}). What does it mean?",
    "conflicting_stakeholder_expectations": "{id} conflicts with another stakeholder's requirement ({detail}). Which expectation should prevail?",
    "missing_controls": "{id} lacks a required control ({detail}). Which control should apply?",
}


def _owner(item: dict, check: str) -> str:
    """Route to the stakeholder who gave the requirement, else to the role that owns the check or category."""
    if item.get("stakeholder_role"):
        return item["stakeholder_role"]
    if check in CHECK_OWNER:
        return CHECK_OWNER[check]
    owners = [r.id for r in get_catalog().roles if set(item["categories"]) & set(r.categories.primary)]
    return owners[0] if owners else "business_analyst"


def _fallback_questions(returned: list[dict], covered: set[str]) -> list[dict]:
    out = []
    for item in returned:
        if item["req_id"] in covered:
            continue
        worst = sorted(item["checks"], key=lambda c: (c["check"] not in BLOCKING_CHECKS, c["severity"] != "high"))[0]
        out.append({"question": FALLBACK[worst["check"]].format(id=item["req_id"], detail=worst["message"][:160]),
                    "target_role": _owner(item, worst["check"]), "related_req_ids": [item["req_id"]],
                    "severity": "blocking" if item["blocking"] else "non_blocking",
                    "reason": f"Failed check: {QUALITY_CHECKS[worst['check']]}", "origin": "validation"})
    return out


def clarification(state: ProjectState) -> ProjectState:
    domain = get_catalog().domain(state["domain"])
    returned = state.get("returned", [])
    reqs = [r for r in state["requirements"] if r.get("status") != "suggested"]
    text = "\n".join(r["statement"] for r in reqs)
    defined, undefined = terms_in(text)
    history = search(text[:2000] or domain_name(state["domain"]), agent="clarification_agent",
                     collections=["project_history"], domain=state["domain"], k=4) if text else []
    result = llm.structured(ClarificationResult, PROMPT.format(
        defined="; ".join(f"{d['acronym'] or d['term']}: {d['definition'][:120]}" for d in defined[:25]) or "none",
        undefined=", ".join(undefined) or "none", history=evidence_block(history, 4000) or "(no previous projects)",
        domain=domain_name(state["domain"]), mandatory=", ".join(domain.mandatory_categories) if domain else "-",
        returned="\n".join(f"- [{i['req_id']}] failed {', '.join(c['check'] for c in i['checks'])}: "
                           + "; ".join(c["message"][:140] for c in i["checks"][:3]) for i in returned) or "(none)",
        roles=roles_reference(), limit=max(12, len(returned) + 4), requirements=format_requirements(reqs, with_source=True)))
    questions = [q.model_dump() | {"origin": "clarification_agent"} for q in result.questions]

    # A returned requirement that fails a blocking check keeps its question blocking, whatever the LLM said.
    blocking_ids = {i["req_id"] for i in returned if i["blocking"]}
    for q in questions:
        if blocking_ids & set(q["related_req_ids"]):
            q["severity"] = "blocking"
    covered = {i for q in questions for i in q["related_req_ids"]}
    questions += _fallback_questions(returned, covered)

    catalog = get_catalog()
    issues = [*state.get("issues", []), *({
        "req_id": ", ".join(q["related_req_ids"]) or None, "type": "clarification_needed", "check": None,
        "message": f"{q['question']} (ask {catalog.role(q['target_role']).name})",
        "severity": "high" if q["severity"] == "blocking" else "low"} for q in questions)]
    record(state["project_id"], "clarification_agent", "questions_raised",
           {"total": len(questions), "blocking": sum(q["severity"] == "blocking" for q in questions),
            "returned_requirements": len(returned),
            "covered_by_fallback": sum(q["origin"] == "validation" for q in questions)})
    return {"clarifications": questions, "issues": issues}
