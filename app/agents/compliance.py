"""Compliance agent: maps requirements to regulations/policies with knowledge-base evidence, and finds gaps.

Standard (step 11). For every mapping it determines the jurisdiction and regulation, the required security or
privacy controls, the supporting evidence, and the obligation type (data retention, reporting, ...). It also lists
compliance gaps and the mandatory approval or audit checkpoints.

It never makes final legal determinations. Every output is a *proposed* mapping; high-impact interpretations, and
mappings without strong retrieved evidence, are flagged for compliance/legal review. The human-approval agent then
makes compliance & legal a required approver of the baseline.
"""

from app import llm
from app.agents.common import domain_name, format_requirements, known_ids
from app.audit import record
from app.catalog.loader import get_catalog
from app.config import get_settings
from app.graph.state import ProjectState
from app.kb.retrieval import evidence_block, rewrite_queries, search
from app.schemas import ComplianceResult

PROMPT = """You are the compliance agent for a {domain} project (jurisdiction: {jurisdiction}).
Map requirements to the regulations, standards or policies they help satisfy, and identify obligations in the
evidence that no requirement covers (gaps). You propose mappings; you do NOT make final legal determinations.

For each mapping determine:
- jurisdiction (e.g. IN, EU, GLOBAL) and the regulation, standard or policy;
- obligation_type: data_retention, reporting, consent_privacy, security_control, disclosure, kyc_aml, audit_trail
  or other; for retention or reporting give the period in retention_period (e.g. "8 years", "monthly");
- required_controls: the security or privacy controls the obligation requires (e.g. "encryption at rest",
  "maker-checker approval", "consent capture");
- impact: high when a wrong interpretation could bring penalties, licence action or customer harm.
Also list checkpoints: mandatory approval or audit checkpoints the regulations impose on the project (e.g. compliance
sign-off before go-live, periodic access review, regulatory filing), with the stage, approving role and regulation.

Evidence rules:
- Cite the knowledge-base passages in <evidence>: quote them verbatim in `evidence` and give their ref (e.g. KB-31).
- Prefer passages marked "evidence strength strong"; a weak passage may be cited but set needs_legal_review = true.
- Catalog hints are unverified: cite them as evidence_ref "catalog", keep confidence <= 0.6, needs_legal_review = true.
- If nothing supports a mapping, use evidence_ref "none" and needs_legal_review = true. Never invent a citation.
- Only map requirements with a real regulatory, privacy, security or audit dimension.

Catalog hints (typical regulations for this domain, applicability unconfirmed): {regulations}

<evidence>
{evidence}
</evidence>

Requirements:
{requirements}"""

DETERMINATION = "Proposed mapping by the compliance agent; not a legal determination."


def compliance(state: ProjectState) -> ProjectState:
    reqs = state["requirements"]
    domain = get_catalog().domain(state["domain"])
    jurisdiction = state.get("jurisdiction", "IN")
    relevant = [r for r in reqs if {"regulatory", "privacy", "security", "audit", "data"} & set(r["categories"])] or reqs
    statements = "\n".join(r["statement"] for r in relevant[:25])
    queries = rewrite_queries(statements, "regulatory obligations and policy controls") \
        if get_settings().kb_query_rewrite and statements else [statements]
    hits = search(queries, agent="compliance_agent", domain=state["domain"], jurisdiction=jurisdiction, k=10)

    result = llm.structured(ComplianceResult, PROMPT.format(
        domain=domain_name(state["domain"]), jurisdiction=jurisdiction,
        regulations="; ".join(domain.typical_regulations) if domain else "-",
        evidence=evidence_block(hits) or "(no applicable knowledge-base passages)", requirements=format_requirements(reqs)))
    ids = known_ids(reqs)
    by_ref = {h.ref: h for h in hits}
    mappings = []
    for m in result.mappings:
        if m.req_id not in ids:
            continue
        m = m.model_dump() | {"determination": DETERMINATION}
        hit = by_ref.get(m["evidence_ref"])
        if hit is None:  # citation not backed by retrieved evidence → downgrade and send to legal review
            m["needs_legal_review"] = True
            m["confidence"] = min(m["confidence"], 0.6)
            if m["evidence_ref"] not in ("catalog", "none"):
                m["evidence_ref"], m["evidence"] = "none", ""
            m["jurisdiction"] = m["jurisdiction"] or jurisdiction
        else:
            m["citation"], m["evidence_strength"] = hit.citation, hit.strength
            m["jurisdiction"] = ", ".join(hit.jurisdictions)  # the evidence's own jurisdiction, not the model's guess
            if hit.strength != "strong":
                m["needs_legal_review"] = True
        if m["impact"] == "high":  # high-impact interpretations always need compliance/legal approval
            m["needs_legal_review"] = True
        mappings.append(m)
    for n, m in enumerate(mappings, 1):  # stable IDs so humans can decide on each interpretation (step 16)
        m["id"] = f"MAP-{n:02d}"
    gaps = [g.model_dump() for g in result.gaps]
    checkpoints = [c.model_dump() | {"req_ids": [i for i in c.req_ids if i in ids]} for c in result.checkpoints]
    obligations = [{"kind": m["obligation_type"], "regulation": m["regulation"], "jurisdiction": m["jurisdiction"],
                    "obligation": m["obligation"], "period": m["retention_period"], "req_id": m["req_id"],
                    "evidence_ref": m["evidence_ref"], "citation": m.get("citation")}
                   for m in mappings if m["obligation_type"] in ("data_retention", "reporting")]
    record(state["project_id"], "compliance_agent", "mapped_compliance",
           {"queries": queries, "evidence_passages": len(hits), "mappings": len(mappings), "gaps": len(gaps),
            "checkpoints": len(checkpoints), "retention_and_reporting": len(obligations),
            "high_impact": sum(m["impact"] == "high" for m in mappings),
            "needs_legal_review": sum(m["needs_legal_review"] for m in mappings)})
    return {"compliance": {"mappings": mappings, "gaps": gaps, "checkpoints": checkpoints,
                           "retention_and_reporting": obligations, "queries": queries, "determination": DETERMINATION,
                           "evidence": [{k: v for k, v in h.to_dict().items() if k not in ("context", "passage")} for h in hits]}}
