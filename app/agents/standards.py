"""The output standards every analysis agent is held to (problem statement steps 8-13).

One definition, used by the agents that produce the outputs, by the tests that check them and by
guide/agent_standards.md. `standard_record()` is the step-8 view of a requirement used by the API and artefacts.
"""

import re

# ---------- Step 8: standard requirement structure ----------

REQUIREMENT_FIELDS = [
    ("id", "Requirement ID"), ("statement", "Requirement statement"), ("categories", "Requirement category"),
    ("source_stakeholder", "Source stakeholder"), ("business_justification", "Business justification"),
    ("priority", "Priority"), ("dependencies", "Dependencies"), ("assumptions", "Assumptions"),
    ("acceptance_criteria", "Acceptance criteria"), ("applicable_regulations", "Applicable regulations"),
    ("risk_level", "Risk level"), ("confidence", "Confidence score"), ("approval_status", "Approval status"),
]


def standard_record(r: dict) -> dict:
    """A requirement in the standard 13-field structure, plus its trace back to the source statement."""
    return {
        "id": r["id"], "statement": r["statement"], "categories": r["categories"],
        "source_stakeholder": r.get("stakeholder_role") or r.get("origin"),
        "business_justification": r.get("business_justification", ""), "priority": r["priority"],
        "dependencies": [*r.get("depends_on", []), *r.get("dependencies", [])], "assumptions": r.get("assumptions", []),
        "acceptance_criteria": r["acceptance_criteria"], "applicable_regulations": r.get("applicable_regulations", []),
        "risk_level": r.get("risk_level", "low"), "confidence": r["confidence"], "approval_status": r.get("status", "proposed"),
        "trace": trace(r),
    }


def trace(r: dict) -> dict:
    """Link to the original stakeholder statement and supporting document (step 12)."""
    return {"req_id": r["id"], "stakeholder_role": r.get("stakeholder_role"), "source_id": r.get("source_id"),
            "source_title": r.get("source_title"), "source_quote": r.get("source_quote", ""),
            "citations": [c["citation"] for c in r.get("citations", [])]}


# ---------- Step 10: requirement-quality checks ----------

QUALITY_CHECKS = {
    "ambiguity": "Vague or unmeasurable wording",
    "incompleteness": "Missing actor, trigger, condition, threshold, data or error handling; or missing record fields",
    "inconsistency": "Contradicts another requirement or an approved policy/regulation",
    "duplication": "Same as, or overlapping with, another requirement",
    "infeasibility": "Cannot be achieved technically, economically or legally as stated",
    "lack_of_testability": "No verifiable acceptance criteria",
    "missing_source": "No supporting stakeholder statement, or the quote is not in the source",
    "undefined_terminology": "Uses a term or acronym the glossary does not define",
    "conflicting_stakeholder_expectations": "Stakeholders in different roles want incompatible things",
    "missing_controls": "A security or compliance control the requirement needs is absent",
}
# Failures that must be resolved before the baseline can be approved (the clarification gate pauses for them).
BLOCKING_CHECKS = {"missing_source", "infeasibility", "conflicting_stakeholder_expectations", "inconsistency"}
# Which roles own a check's fix when the requirement has no source stakeholder.
CHECK_OWNER = {"missing_controls": "infosec", "infeasibility": "architect_developer", "inconsistency": "business_analyst"}

# ---------- Step 11: compliance determinations ----------

COMPLIANCE_DETERMINATIONS = [
    ("jurisdiction", "Applicable jurisdiction and regulation"),
    ("required_controls", "Required security or privacy control"),
    ("evidence", "Evidence supporting the mapping"),
    ("gaps", "Compliance gaps"),
    ("checkpoints", "Mandatory approval or audit checkpoints"),
    ("retention_and_reporting", "Data-retention and reporting obligations"),
]

# ---------- Step 12: artefacts ----------

ARTEFACTS = [
    ("srs_markdown", "Software Requirements Specification"),
    ("user_stories", "User stories and acceptance criteria"),
    ("use_cases", "Use-case descriptions"),
    ("process_workflows", "Process workflows"),
    ("data_requirements", "Data requirements"),
    ("interface_requirements", "Interface requirements"),
    ("threat_risk_register", "Threat and risk register"),
    ("compliance_matrix", "Compliance-control matrix"),
    ("traceability_matrix", "Requirements Traceability Matrix"),
    ("assumptions_dependencies", "Assumptions and dependency register"),
    ("open_issues", "Open-issues list"),
]

# ---------- Step 13: SDLC decision factors ----------

SDLC_FACTORS = [
    ("requirement_stability", "Requirement stability"), ("regulatory_criticality", "Regulatory criticality"),
    ("security_risk", "Security risk"), ("complexity", "Project complexity"), ("system_size", "System size"),
    ("legacy_dependence", "Legacy-system dependence"), ("change_frequency", "Frequency of expected changes"),
    ("continuous_delivery_need", "Need for continuous delivery"), ("stakeholder_availability", "Availability of stakeholders"),
    ("testing_documentation_need", "Testing and documentation requirements"),
    ("budget_schedule_constraint", "Budget and schedule constraints"),
    ("formal_verification_need", "Need for formal verification"), ("failure_consequence", "Consequences of system failure"),
]


# ---------- Shared deterministic helpers ----------

def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s<>]", " ", (text or "").lower()).split())


def quote_in_source(quote: str, source_text: str) -> str:
    """'exact' when the quote appears in the source, 'paraphrased' when most of its words do, else 'not_found'."""
    q, s = _norm(quote), _norm(source_text)
    if not q:
        return "not_found"
    if q in s:
        return "exact"
    words = q.split()
    present = sum(w in set(s.split()) for w in words)
    return "paraphrased" if words and present / len(words) >= 0.8 else "not_found"
