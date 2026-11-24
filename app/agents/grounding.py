"""Grounding agent (step 6): checks every requirement against approved sources.

Runs in parallel with the other analysis agents. For each requirement it
  1. classifies what evidence is needed (from its categories → knowledge collections),
  2. retrieves that evidence for the requirement itself,
  3-4. asks the LLM, with the evidence, whether the requirement is supported, contradicted or unsupported,
  5. attaches verified citations and a combined confidence score,
  6. marks requirements that must be escalated to a human (contradiction, missing obligation, low confidence).
"""

from app import llm
from app.agents.common import domain_name
from app.audit import record
from app.graph.state import ProjectState
from app.kb.grounding import (best_strength, collections_for_requirement, requirement_confidence,
                              requirement_escalation)
from app.kb.retrieval import Hit, search
from app.schemas import GroundingResult

BATCH = 8

PROMPT = """You are the grounding agent for a {domain} project (jurisdiction {jurisdiction}). For each requirement,
judge it against the approved evidence retrieved FOR THAT REQUIREMENT:
- supported / partially_supported: the evidence backs it (cite the refs);
- contradicts_evidence: it conflicts with a policy or regulation (e.g. a higher limit, shorter retention, weaker
  authentication, a missing mandatory approval) — cite the conflicting refs and say what differs;
- unsupported: an obligation of this kind would normally come from a regulation or policy, but none was retrieved;
- no_obligation_expected: a product feature or preference that needs no regulatory or policy grounding.
Only cite refs listed under that requirement. Never invent refs.

{blocks}"""


def _block(req: dict, hits: list[Hit]) -> str:
    # Token saving: the matched passage itself (not its whole parent section), capped at 450 characters
    evidence = "\n".join(f"  [{h.ref}] {h.citation} (strength {h.strength}): {(h.passage or h.context)[:450]}"
                         for h in hits) or "  (no evidence retrieved)"
    return f"[{req['id']}] ({', '.join(req['categories'])}) {req['statement']}\nEvidence:\n{evidence}"


def grounding(state: ProjectState) -> ProjectState:
    reqs = [r for r in state["requirements"] if r.get("status") != "suggested"]
    retrieved: dict[str, list[Hit]] = {}
    for r in reqs:                                                     # 1-2. classify → retrieve per requirement
        cols = collections_for_requirement(r["categories"])
        retrieved[r["id"]] = search(r["statement"], agent="grounding_agent", collections=cols, domain=state["domain"],
                                    jurisdiction=state.get("jurisdiction"), k=3) if cols else []

    verdicts: dict[str, dict] = {}
    for i in range(0, len(reqs), BATCH):                               # 3-4. evidence → verdict
        batch = reqs[i:i + BATCH]
        result = llm.structured(GroundingResult, PROMPT.format(
            domain=domain_name(state["domain"]), jurisdiction=state.get("jurisdiction", "n/a"),
            blocks="\n\n".join(_block(r, retrieved[r["id"]]) for r in batch)))
        verdicts.update({v.req_id: v.model_dump() for v in result.items})

    out: dict[str, dict] = {}
    for r in reqs:                                                     # 5-6. citations, confidence, escalation
        hits = {h.ref: h for h in retrieved[r["id"]]}
        v = verdicts.get(r["id"]) or {"support": "unsupported" if hits else "no_obligation_expected", "refs": [],
                                      "note": "No verdict returned", "confidence": 0.5}
        refs = [x for x in v["refs"] if x in hits]                     # drop citations to passages not retrieved
        strength = best_strength(refs, hits)
        confidence = requirement_confidence(r["confidence"], v["support"], v["confidence"], strength)
        out[r["id"]] = {
            "support": v["support"], "note": v["note"], "collections": collections_for_requirement(r["categories"]),
            "citations": [{"ref": x, "citation": hits[x].citation, "strength": hits[x].strength, "issuer": hits[x].issuer,
                           "version": hits[x].version, "doc_key": hits[x].doc_key} for x in refs],
            "dropped_refs": [x for x in v["refs"] if x not in hits],
            "grounding_confidence": v["confidence"], "evidence_strength": strength, "confidence": confidence,
            "escalation_reasons": requirement_escalation(r["categories"], v["support"], confidence),
        }
    record(state["project_id"], "grounding_agent", "grounded_requirements", {
        "requirements": len(out),
        "by_support": {s: sum(g["support"] == s for g in out.values()) for s in
                       ("supported", "partially_supported", "unsupported", "contradicts_evidence", "no_obligation_expected")},
        "escalated": sum(bool(g["escalation_reasons"]) for g in out.values())})
    return {"grounding": out}
