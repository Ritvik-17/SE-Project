"""Validation agent: verifies completeness, consistency and evidence; aggregates every agent's findings.

Deterministic (no LLM) so the gate decision is reproducible.

Standards applied:
- step 8: completes the standard record (applicable regulations from compliance, risk level from the risk register
  and security findings);
- step 10: tags every finding with one of the ten quality checks (standards.QUALITY_CHECKS) and returns the
  requirements that fail any of them to the clarification agent (`returned`), which runs next.
"""

import re

from app.agents.risk import risk_level
from app.agents.standards import BLOCKING_CHECKS, QUALITY_CHECKS, quote_in_source
from app.audit import record
from app.catalog.loader import get_catalog
from app.config import get_settings
from app.graph.state import ProjectState
from app.kb.lookup import glossary, terms_in

VAGUE_TERMS = re.compile(
    r"\b(fast|quick(ly)?|user[- ]friendly|easy|simple|robust|flexible|adequate|appropriate|"
    r"as needed|etc\.?|secure(ly)?|efficient(ly)?|minimal|seamless(ly)?)\b",
    re.IGNORECASE,
)
PRIORITY_BY_SEVERITY = {"high": "must", "medium": "should", "low": "could"}
LEVELS = ("low", "medium", "high")
QUALITY_TYPE = {"ambiguity": "ambiguous", "incompleteness": "incomplete", "infeasibility": "infeasible",
                "lack_of_testability": "not_testable"}


def _risk_level(req_id: str, state: ProjectState) -> str:
    """Highest level among the risks and security findings linked to the requirement (step 8 risk level)."""
    levels = [rk["level"] for rk in state.get("risks", []) if req_id in rk["related_req_ids"]]
    levels += [f["severity"] for f in state.get("security_findings", []) if f.get("req_id") == req_id]
    return max(levels, key=LEVELS.index) if levels else "low"


def _suggestions(state: ProjectState) -> list[dict]:
    """Agent-proposed requirements (security controls, compliance gaps). Excluded from the baseline unless accepted."""
    out = []
    common = {"type": "non_functional", "acceptance_criteria": [], "source_quote": "", "status": "suggested",
              "source_id": None, "source_type": None, "stakeholder_role": None, "assumptions": [], "dependencies": [],
              "applicable_regulations": []}
    for n, f in enumerate(state.get("security_findings", []), 1):
        out.append(common | {"id": f"SUG-SEC-{n:03d}", "statement": f["suggested_requirement"],
                             "categories": f["categories"] or ["security"], "priority": PRIORITY_BY_SEVERITY[f["severity"]],
                             "confidence": 0.6, "origin": "security_privacy_agent", "rationale": f["description"],
                             "business_justification": f["description"], "risk_level": f["severity"],
                             "source_title": "Security & privacy agent"})
    for n, g in enumerate(state.get("compliance", {}).get("gaps", []), 1):
        out.append(common | {"id": f"SUG-CMP-{n:03d}", "statement": g["suggested_requirement"],
                             "categories": g["categories"] or ["regulatory"], "priority": "must", "confidence": 0.5,
                             "origin": "compliance_agent", "rationale": f"{g['regulation']}: {g['description']}",
                             "business_justification": f"Closes a compliance gap: {g['description']}",
                             "applicable_regulations": [g["regulation"]], "risk_level": "high",
                             "source_title": "Compliance agent"})
    return out


def validation(state: ProjectState) -> ProjectState:
    catalog = get_catalog()
    threshold = get_settings().confidence_threshold
    reqs = [r for r in state["requirements"] if r.get("origin") != "security_privacy_agent" and r.get("origin") != "compliance_agent"]
    issues: list[dict] = []

    # Step 6.5-6.6: attach grounding citations, replace confidence with the combined score, mark escalations
    grounded = state.get("grounding", {})
    mappings = state.get("compliance", {}).get("mappings", [])
    merged = []
    for r in reqs:
        g = grounded.get(r["id"])
        if g:
            r = r | {"extraction_confidence": r.get("extraction_confidence", r["confidence"]), "confidence": g["confidence"],
                     "grounding_support": g["support"], "grounding_note": g["note"], "citations": g["citations"],
                     "escalated": bool(g["escalation_reasons"]), "escalation_reasons": g["escalation_reasons"]}
        # Step 8: complete the standard record
        r = r | {"applicable_regulations": sorted({m["regulation"] for m in mappings if m["req_id"] == r["id"]}),
                 "risk_level": _risk_level(r["id"], state)}
        merged.append(r)
    reqs = merged
    roles_of = {r["id"]: r.get("stakeholder_role") for r in reqs}
    texts = {s["id"]: s.get("text", "") for s in state.get("sources", [])}

    def issue(kind: str, message: str, req_id: str | None = None, severity: str = "medium", check: str | None = None) -> None:
        issues.append({"req_id": req_id, "type": kind, "message": message, "severity": severity, "check": check})

    # Per-requirement quality rules
    terms = glossary()
    for r in reqs:
        if terms:
            for acronym in terms_in(r["statement"], terms)[1]:
                issue("undefined_term", f"'{acronym}' is not defined in the glossary", r["id"], "low", "undefined_terminology")
        if r["confidence"] < threshold:
            issue("low_confidence", f"Confidence {r['confidence']:.2f} below {threshold}", r["id"])
        if not r["acceptance_criteria"]:
            issue("not_testable", "No acceptance criteria", r["id"], "medium", "lack_of_testability")
        if not r.get("business_justification", "").strip():
            issue("incomplete", "No business justification", r["id"], "low", "incompleteness")
        # Missing source: no quote, or a quote that cannot be found in the source it claims to come from
        if not r.get("source_quote", "").strip() or r.get("source_id") is None:
            issue("missing_evidence", "No supporting quote from the source", r["id"], "high", "missing_source")
        elif r["source_id"] in texts:
            found = quote_in_source(r["source_quote"], texts[r["source_id"]])
            if found == "not_found":
                issue("missing_evidence", f"Quote not found in '{r.get('source_title')}'", r["id"], "high", "missing_source")
            elif found == "paraphrased":
                issue("paraphrased_quote", "Quote is paraphrased, not verbatim", r["id"], "low", "missing_source")
        if m := VAGUE_TERMS.search(r["statement"]):
            issue("ambiguous", f"Vague term '{m.group(0)}'", r["id"], "medium", "ambiguity")
        role = catalog.role(r["stakeholder_role"]) if r.get("stakeholder_role") else None
        if role:
            for cat in set(r["categories"]) - set(role.categories.primary + role.categories.secondary):
                owners = [x.name for x in catalog.roles if cat in x.categories.primary]
                issue("outside_role_authority", f"'{cat}' requirement from {role.name}; confirm with {', '.join(owners)}", r["id"], "low")

    # Findings from the specialist agents
    for f in state.get("quality_findings", []):
        sev = "high" if f["check"] == "infeasibility" else "medium"
        issue(QUALITY_TYPE[f["check"]], f"{f['explanation']} → {f['suggested_fix']}", f["req_id"], sev, f["check"])
    for r in reqs:
        if r.get("grounding_support") == "contradicts_evidence":
            refs = ", ".join(c["citation"] for c in r.get("citations", [])) or "an approved source"
            issue("contradicts_policy", f"Conflicts with {refs}: {r['grounding_note']}", r["id"], "high", "inconsistency")
        elif r.get("escalated"):
            issue("escalated", "; ".join(r["escalation_reasons"]), r["id"], "medium")
    for c in state.get("conflicts", []):
        roles = {roles_of.get(i) for i in c["req_ids"]} - {None}
        if c["kind"] == "conflict":
            check = "conflicting_stakeholder_expectations" if len(roles) > 1 else "inconsistency"
        else:
            check = "duplication"
        for req_id in c["req_ids"]:  # one issue per requirement, so each can be returned for clarification
            others = ", ".join(i for i in c["req_ids"] if i != req_id)
            issue(c["kind"], f"With {others}: {c['description']} → {c['suggested_resolution']}", req_id,
                  "high" if c["kind"] == "conflict" else "medium", check)
    for m in mappings:
        if m["needs_legal_review"]:
            issue("legal_review", f"{m['regulation']}: {m['obligation']} — interpretation needs compliance/legal review", m["req_id"], "medium")
    for f in state.get("security_findings", []):
        if f["severity"] == "high":
            issue("security_gap", f["description"], f["req_id"], "high", "missing_controls")
        elif f.get("req_id"):
            issue("security_weakness", f["description"], f["req_id"], f["severity"], "missing_controls")
    for g in state.get("compliance", {}).get("gaps", []):
        issue("compliance_gap", f"{g['regulation']}: {g['description']}", None, "high", "missing_controls")
    for rk in state.get("risks", []):
        if risk_level(rk["score"]) == "high":
            issue("high_risk", f"{rk['id']} {rk['title']} (score {rk['score']})", ", ".join(rk["related_req_ids"]) or None, "high")
    for s in state.get("sources", []):
        if s["injection_flags"]:
            issue("prompt_injection", f"Source '{s['title']}' contains instruction-like text: {s['injection_flags']}", None, "high")

    # Domain completeness
    domain = catalog.domain(state["domain"])
    covered_roles = {s["stakeholder_role"] for s in state.get("sources", []) if s["stakeholder_role"]}
    covered_cats = {c for r in reqs for c in r["categories"]}
    missing_roles = [x for x in domain.required_roles if x not in covered_roles] if domain else []
    missing_cats = [x for x in domain.mandatory_categories if x not in covered_cats] if domain else []
    for x in missing_roles:
        issue("missing_stakeholder", f"No input from {catalog.role(x).name}", None, "medium")
    for x in missing_cats:
        issue("missing_coverage", f"No {x} requirements (mandatory for {domain.name})", None, "high", "incompleteness")

    # Quality scores (0-1)
    n = len(reqs) or 1
    in_conflict = {i for c in state.get("conflicts", []) if c["kind"] == "conflict" for i in c["req_ids"]}
    completeness = 0.0
    if domain:
        completeness = 0.5 * (1 - len(missing_cats) / len(domain.mandatory_categories)) \
            + 0.5 * (1 - len(missing_roles) / len(domain.required_roles))
    quality = {
        "completeness": round(completeness, 2),
        "consistency": round(1 - len(in_conflict) / n, 2),
        "evidence": round(sum(bool(r.get("source_quote", "").strip()) and r["confidence"] >= threshold for r in reqs) / n, 2),
        "testability": round(sum(bool(r["acceptance_criteria"]) for r in reqs) / n, 2),
    }
    needs = [r for r in reqs if r.get("grounding_support") not in (None, "no_obligation_expected")]
    quality["grounding"] = round(sum(r["grounding_support"] in ("supported", "partially_supported") for r in needs)
                                 / len(needs), 2) if needs else 1.0
    quality["overall"] = round(sum(quality.values()) / 5, 2)

    # Step 10: requirements failing a check (medium or high) go back to the clarification agent
    failed: dict[str, list[dict]] = {}
    for i in issues:
        if i["check"] and i["req_id"] in roles_of and i["severity"] != "low":
            failed.setdefault(i["req_id"], []).append({"check": i["check"], "message": i["message"], "severity": i["severity"]})
    by_id = {r["id"]: r for r in reqs}
    returned = [{"req_id": rid, "statement": by_id[rid]["statement"], "stakeholder_role": by_id[rid].get("stakeholder_role"),
                 "categories": by_id[rid]["categories"], "checks": checks,
                 "blocking": any(c["check"] in BLOCKING_CHECKS and c["severity"] == "high" for c in checks)}
                for rid, checks in failed.items()]
    quality["checks"] = {c: len({i["req_id"] for i in issues if i["check"] == c}) for c in QUALITY_CHECKS}
    quality["requirements_passing"] = round(1 - len(failed) / n, 2)

    suggestions = _suggestions(state)
    record(state["project_id"], "validation_agent", "validated",
           {"issues": len(issues), "high": sum(i["severity"] == "high" for i in issues),
            "returned_for_clarification": len(returned), "suggested_requirements": len(suggestions), "quality": quality})
    return {"issues": issues, "quality": quality, "requirements": reqs + suggestions, "returned": returned}
