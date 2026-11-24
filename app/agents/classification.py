"""Classification agent: normalises type (FR/NFR), multi-label categories and priority across all requirements.

Standard (step 9): every requirement gets one or more of the 13 categories (multi-label); none may be left without
a category. It also links dependencies between requirements (step 8), since only this agent sees the whole set.
"""

from app import llm
from app.agents.common import domain_name, format_requirements
from app.audit import record
from app.catalog.loader import get_catalog
from app.graph.state import ProjectState
from app.schemas import ClassificationResult

PROMPT = """Classify each requirement of a {domain} system. Requirements were extracted from different sources
independently, so make the classification consistent across the whole set.

Categories (multi-label, assign every one that applies):
{categories}

Type: functional = behaviour the system performs; non_functional = quality, constraint or obligation.
Priority (MoSCoW): must = legal/regulatory or core to the business objective; should = important; could = nice to have.

depends_on: IDs of other requirements in this list that must exist for this one to work (e.g. a disbursement
requirement depends on the approval requirement). Leave empty when there is no such dependency.

Return one item per requirement ID, using the IDs exactly as given.

Requirements:
{requirements}"""


def classification(state: ProjectState) -> ProjectState:
    reqs = state["requirements"]
    if not reqs:
        return {}
    cats = "\n".join(f"- {c.id}: {c.description}" for c in get_catalog().categories)
    result = llm.structured(ClassificationResult, PROMPT.format(
        domain=domain_name(state["domain"]), categories=cats, requirements=format_requirements(reqs)))
    by_id = {i.id: i for i in result.items}
    ids = {r["id"] for r in reqs}
    updated, changed = [], 0
    for r in reqs:
        item = by_id.get(r["id"])
        if item:
            # Multi-label guard: never replace the extractor's categories with an empty set.
            cats = list(dict.fromkeys(item.categories)) or r["categories"]
            changed += (item.type != r["type"]) or (set(cats) != set(r["categories"])) or (item.priority != r["priority"])
            r = r | {"type": item.type, "categories": cats, "priority": item.priority,
                     "classification_rationale": item.rationale,
                     "depends_on": [d for d in dict.fromkeys(item.depends_on) if d in ids and d != r["id"]]}
        if not r["categories"]:
            r = r | {"categories": ["functional" if r["type"] == "functional" else "operational"]}
        updated.append(r)
    record(state["project_id"], "classification_agent", "classified",
           {"requirements": len(reqs), "changed": changed, "unclassified": len(ids - by_id.keys()),
            "multi_label": sum(len(r["categories"]) > 1 for r in updated),
            "dependencies": sum(len(r.get("depends_on", [])) for r in updated)})
    return {"requirements": updated}
