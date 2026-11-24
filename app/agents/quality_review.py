"""Quality-review agent: the semantic requirement-quality checks of step 10.

Checks that need judgement rather than pattern matching: ambiguity, incompleteness, infeasibility and lack of
testability (including acceptance criteria that exist but cannot be verified). The deterministic checks
(missing source, undefined terminology, duplicates, etc.) run in the validation agent.
"""

from app import llm
from app.agents.common import domain_name, known_ids
from app.audit import record
from app.graph.state import ProjectState
from app.schemas import QualityReviewResult

PROMPT = """You are the requirement-quality reviewer for a {domain} system at a bank. Check each requirement for:
- ambiguity: words with more than one reading or no measurable meaning ("fast", "secure", "appropriate", "large
  amounts", "as needed"), or an unclear subject ("it", "they", "the user" where several users exist);
- incompleteness: a missing actor, trigger, condition, threshold, unit, data item or error/exception handling that
  is needed to build it; or a missing business justification;
- infeasibility: cannot be achieved as stated: absolute guarantees ("100% uptime", "zero fraud", "never fails"),
  physically or economically unrealistic targets, or something the law does not allow;
- lack_of_testability: no acceptance criteria, or criteria that cannot be verified by a test or inspection.
Report only real problems; a requirement may have several. Quote the problem words in the explanation, and give a
concrete fix (a rewritten "The system shall ..." statement, or the exact information that is missing).

Requirements (ID, statement, acceptance criteria, justification):
{requirements}"""


def _listing(reqs: list[dict]) -> str:
    return "\n".join(f"[{r['id']}] {r['statement']}\n  criteria: {' | '.join(r['acceptance_criteria']) or 'none'}\n"
                     f"  justification: {r.get('business_justification') or 'none'}" for r in reqs)


def quality_review(state: ProjectState) -> ProjectState:
    reqs = state["requirements"]
    if not reqs:
        return {"quality_findings": []}
    findings: list[dict] = []
    ids = known_ids(reqs)
    for start in range(0, len(reqs), 25):  # batches keep each prompt focused
        result = llm.structured(QualityReviewResult, PROMPT.format(
            domain=domain_name(state["domain"]), requirements=_listing(reqs[start:start + 25])))
        findings += [f.model_dump() for f in result.findings if f.req_id in ids]  # drop hallucinated IDs
    record(state["project_id"], "quality_review_agent", "reviewed_quality",
           {check: sum(f["check"] == check for f in findings)
            for check in ("ambiguity", "incompleteness", "infeasibility", "lack_of_testability")})
    return {"quality_findings": findings}
