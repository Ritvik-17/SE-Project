"""Requirement-extraction agent: turns one masked source chunk into candidate requirements.

Standard (step 8): every requirement carries a statement, categories, priority, business justification,
assumptions, dependencies, acceptance criteria, a verbatim source quote and a confidence score. The coordinator
adds the ID and source stakeholder; later agents add regulations, risk level and approval status.
"""

from app import llm
from app.agents.common import domain_name
from app.audit import record
from app.catalog.loader import get_catalog
from app.graph.state import ProjectState
from app.kb.lookup import in_force
from app.schemas import ExtractionResult
from app.security.filters import REMOVED, neutralise

PROMPT = """Extract every distinct requirement for a {domain} system from the source below.

Source type: {source_type}
How to treat this source: {guidance}
{role_block}
Rules:
- Only extract requirements supported by the content; quote the supporting text verbatim in source_quote.
- Split compound statements into atomic, testable requirements phrased as "The system shall ...".
- Assign all applicable categories (multi-label) and verifiable acceptance criteria. Use ONLY these category ids:
  {category_ids}. Map anything else onto the closest one (e.g. fraud -> security, reporting -> audit or operational).
- business_justification: the business value, obligation or risk the requirement addresses, as stated or clearly
  implied by the source. Leave it empty rather than invent one.
- assumptions: anything you had to assume that the source does not confirm (e.g. "threshold applies per applicant").
- dependencies: systems, teams, data, third parties or decisions it relies on (e.g. "credit bureau API",
  "approved risk threshold from risk management").
- Lower the confidence when the content is vague, implied, or outside the stakeholder's area of authority.
{guidelines}{feedback}
<source_content>
{text}
</source_content>"""


def _guidelines() -> str:
    doc = in_force("requirement-writing-guidelines")
    if doc is None:
        return ""
    return f"Follow the organisation's requirement-writing guidelines (v{doc.version}):\n{doc.content[:2500]}\n"


def extraction(payload: dict) -> ProjectState:
    catalog = get_catalog()
    src = payload["source"]
    src_type = catalog.source(src["source_type"])
    role = catalog.role(src["stakeholder_role"]) if src["stakeholder_role"] else None
    role_block = ""
    if role:
        role_block = (f"Stakeholder: {role.name}. Authority (primary): {', '.join(role.categories.primary)}; "
                      f"contributes to: {', '.join(role.categories.secondary)}.\n")
    feedback = (f"\nReviewer feedback on the previous attempt (address it):\n{payload['feedback']}\n"
                if payload["feedback"] else "")
    # Step 17: instruction-like passages never reach the model, and nothing extracted may rest on them.
    text, removed = neutralise(payload["text"])
    result = llm.structured(ExtractionResult, PROMPT.format(
        domain=domain_name(payload["domain"]), source_type=src_type.name, guidance=src_type.extraction_guidance,
        role_block=role_block, feedback=feedback, text=text, guidelines=_guidelines(),
        category_ids=", ".join(c.id for c in catalog.categories)))
    reqs = [r.model_dump() for r in result.requirements]
    kept = [r for r in reqs if REMOVED not in r["source_quote"]
            and not any(p.lower() in r["source_quote"].lower() for p in removed)]
    record(payload["project_id"], "extraction_agent", "extracted",
           {"source_id": src["id"], "chunk": payload["chunk"], "requirements": len(kept),
            "injection_neutralised": removed, "dropped_for_injection": len(reqs) - len(kept)})
    return {"extractions": [{"source": src, "requirements": kept}]}
