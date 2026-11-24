"""Security & privacy agent: finds missing controls, weak security requirements and privacy risks,
grounded in security standards and the institution's control policies from the knowledge base."""

from app import llm
from app.agents.common import domain_name, format_requirements, known_ids
from app.audit import record
from app.graph.state import ProjectState
from app.kb.retrieval import evidence_block, search
from app.schemas import SecurityResult

PROMPT = """You are the information-security and privacy agent for a {domain} system at a bank.
Review the requirements and the source sensitivity profile, then report:
- missing_control: an expected control with no requirement (authentication/MFA, authorisation & segregation of duties,
  encryption in transit/at rest, key management, logging & monitoring, fraud controls, session management,
  input validation, third-party/API security, secure SDLC, backup & recovery);
- weak_requirement: a security requirement that is vague, untestable or insufficient (cite its ID);
- privacy_risk: personal-data collection, consent, purpose limitation, retention, masking, data-subject rights,
  cross-border transfer or profiling concerns.
For each finding give a concrete "The system shall ..." requirement and a severity (high = likely breach, fraud loss
or regulatory penalty). When a standard or policy passage in <evidence> supports the finding, put its ref in
evidence_ref (e.g. KB-12); otherwise "none".

Source sensitivity profile: {sensitivity}

<evidence>
{evidence}
</evidence>

Requirements:
{requirements}"""

TOPICS = ["authentication multi-factor step-up", "access control segregation of duties", "encryption key management",
          "security logging monitoring incident", "personal data consent retention masking"]


def security_privacy(state: ProjectState) -> ProjectState:
    reqs = state["requirements"]
    profile = ", ".join(f"{s['title']}: {s['sensitivity']}" for s in state.get("sources", [])) or "n/a"
    hits = search(TOPICS, agent="security_privacy_agent", domain=state["domain"],
                  jurisdiction=state.get("jurisdiction"), k=8)
    result = llm.structured(SecurityResult, PROMPT.format(
        domain=domain_name(state["domain"]), sensitivity=profile, evidence=evidence_block(hits) or "(none available)",
        requirements=format_requirements(reqs)))
    ids, refs = known_ids(reqs), {h.ref: h for h in hits}
    findings = []
    for f in result.findings:
        d = f.model_dump() | {"req_id": f.req_id if f.req_id in ids else None}
        hit = refs.get(d.get("evidence_ref") or "")
        d["evidence_ref"], d["citation"] = (hit.ref, hit.citation) if hit else ("none", None)
        findings.append(d)
    record(state["project_id"], "security_privacy_agent", "assessed_security",
           {"evidence_passages": len(hits)} | {sev: sum(f["severity"] == sev for f in findings) for sev in ("high", "medium", "low")})
    return {"security_findings": findings}
