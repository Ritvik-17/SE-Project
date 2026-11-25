"""Conflict-detection agent: contradictions, duplicates and overlaps between requirements."""

from app import llm
from app.agents.common import format_requirements, known_ids
from app.audit import record
from app.graph.state import ProjectState
from app.schemas import ConflictResult

PROMPT = """Find problems BETWEEN the requirements below (not within a single one):
- conflict: requirements that cannot both be satisfied (contradicting limits, rules, timings, access rights);
- duplicate: requirements that state the same thing;
- overlap: requirements that partly restate each other and should be merged.
Pay attention to conflicting expectations between different stakeholders.
For each problem list the requirement IDs involved and a concrete suggested resolution.
Return an empty list if there are none.

Requirements:
{requirements}"""


def conflict_detection(state: ProjectState) -> ProjectState:
    reqs = state["requirements"]
    found: list[dict] = []
    # Deterministic pass: exact duplicates after normalisation.
    seen: dict[str, str] = {}
    for r in reqs:
        key = " ".join(r["statement"].lower().split())
        if key in seen:
            found.append({"kind": "duplicate", "req_ids": [seen[key], r["id"]],
                          "description": "Identical statements", "suggested_resolution": f"Keep {seen[key]}, reject {r['id']}"})
        seen.setdefault(key, r["id"])
    if len(reqs) > 1:
        result = llm.structured(ConflictResult, PROMPT.format(requirements=format_requirements(reqs, with_source=True)))
        ids = known_ids(reqs)
        exact = {tuple(sorted(c["req_ids"])) for c in found}
        for c in result.conflicts:
            valid = [i for i in c.req_ids if i in ids]  # drop hallucinated IDs
            if len(valid) >= 2 and tuple(sorted(valid)) not in exact:
                found.append(c.model_dump() | {"req_ids": valid})
    record(state["project_id"], "review_agent", "conflicts_detected",
           {kind: sum(c["kind"] == kind for c in found) for kind in ("conflict", "duplicate", "overlap")})
    return {"conflicts": found}
