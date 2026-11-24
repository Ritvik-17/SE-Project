"""Retrieval-grounded generation (problem statement step 6).

    1. classify the stakeholder query or requirement   classify_query() / collections_for_requirement()
    2. retrieve relevant policies, regulations, docs   retrieval.search()
    3. provide retrieved evidence to the LLM           retrieval.evidence_block()
    4. generate the requirement or analysis            ground_answer() / agents.grounding
    5. attach citations and confidence scores          verify_claims(), answer_confidence(), requirement_confidence()
    6. escalate unsupported / low-confidence output    should_escalate*() → review queue / human approval gate

Confidence is never the LLM's self-assessment alone: it is combined with the strength of the retrieved evidence
and the share of claims that carry a valid citation.
"""

from datetime import date

from app import llm
from app.audit import record
from app.config import get_settings
from app.db import SessionLocal
from app.kb.retrieval import Hit, evidence_block, search
from app.models import ReviewItem
from app.schemas import GroundedAnswer, QueryClassification

# Strength of the best retrieved evidence → multiplier on confidence
EVIDENCE_FACTOR = {"strong": 1.0, "weak": 0.6, "none": 0.25}

# Step 6.1 for requirements: deterministic routing from the classification agent's categories to collections.
COLLECTIONS_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    "regulatory": ("regulation", "policy_control"),
    "privacy": ("regulation", "policy_control", "security_standard"),
    "security": ("security_standard", "policy_control"),
    "audit": ("regulation", "policy_control"),
    "data": ("policy_control", "regulation"),
    "business": ("policy_control",),
    "operational": ("policy_control",),
    "availability": ("policy_control", "security_standard"),
    "integration": ("security_standard", "policy_control"),
}
# Categories where an obligation is expected: no evidence means "unsupported", not "no grounding needed".
EVIDENCE_EXPECTED = {"regulatory", "privacy", "security", "audit", "data"}

CLASSIFY_PROMPT = """Classify a stakeholder's question for a requirements-engineering assistant at a bank ({domain}, jurisdiction {jurisdiction}).
Choose the intent, the knowledge collections that could answer it, and 1-3 short search queries.
Collections: regulation (laws, regulator directions), policy_control (the institution's policies and controls),
security_standard (security standards), glossary_process (financial terms, business processes),
re_guideline (how to write requirements), project_history (previously approved projects).
Use out_of_scope with no collections for questions unrelated to financial requirements.

Question: {question}"""

ANSWER_PROMPT = """Answer the stakeholder's question for a {domain} project (jurisdiction {jurisdiction}) using ONLY the evidence.
- Every factual claim must cite the ref(s) of the passage(s) that support it.
- If the evidence does not answer the question, say so plainly, set insufficient_evidence = true and do not guess.
- Do not give legal advice: state what the cited text says.

<evidence>
{evidence}
</evidence>

Question: {question}"""


def collections_for_requirement(categories: list[str]) -> list[str]:
    seen: list[str] = []
    for c in categories:
        for col in COLLECTIONS_BY_CATEGORY.get(c, ()):
            if col not in seen:
                seen.append(col)
    return seen


def evidence_expected(categories: list[str]) -> bool:
    return bool(EVIDENCE_EXPECTED & set(categories))


def best_strength(refs: list[str], hits: dict[str, Hit]) -> str:
    order = {"strong": 2, "weak": 1, "none": 0}
    strengths = [hits[r].strength for r in refs if r in hits]
    return max(strengths, key=order.get) if strengths else "none"


def requirement_confidence(extraction_conf: float, support: str, grounding_conf: float, strength: str) -> float:
    """Final requirement confidence (step 6.5).

    no_obligation_expected → the extraction confidence (nothing to ground).
    otherwise              → ½ extraction + ½ (verdict weight × LLM grounding confidence × evidence factor)
    """
    if support == "no_obligation_expected":
        return round(extraction_conf, 2)
    verdict = {"supported": 1.0, "partially_supported": 0.7, "unsupported": 0.3, "contradicts_evidence": 0.1}[support]
    return round(0.5 * extraction_conf + 0.5 * verdict * grounding_conf * EVIDENCE_FACTOR[strength], 2)


def requirement_escalation(categories: list[str], support: str, confidence: float) -> list[str]:
    """Reasons a requirement must go to human review (step 6.6). Empty list = no escalation."""
    reasons = []
    if support == "contradicts_evidence":
        reasons.append("contradicts an approved policy or regulation")
    if support == "unsupported" and evidence_expected(categories):
        reasons.append("no approved source supports this obligation")
    if confidence < get_settings().grounding_confidence_threshold:
        reasons.append(f"confidence {confidence:.2f} below {get_settings().grounding_confidence_threshold}")
    return reasons


def verify_claims(answer: GroundedAnswer, hits: dict[str, Hit]) -> tuple[list[dict], float]:
    """Keep only citations that point at retrieved passages; return claims and the cited share."""
    claims, cited = [], 0
    for c in answer.claims:
        valid = [r for r in c.refs if r in hits]
        cited += bool(valid)
        claims.append({"text": c.text, "refs": valid, "invalid_refs": [r for r in c.refs if r not in hits],
                       "citations": [hits[r].citation for r in valid]})
    coverage = cited / len(claims) if claims else 0.0
    return claims, coverage


def answer_confidence(llm_conf: float, coverage: float, strength: str, insufficient: bool) -> float:
    """Final answer confidence = LLM confidence × evidence factor × citation coverage (0 if evidence insufficient)."""
    if insufficient:
        return 0.0
    return round(max(0.0, min(1.0, llm_conf)) * EVIDENCE_FACTOR[strength] * coverage, 2)


def classify_query(question: str, domain: str, jurisdiction: str) -> QueryClassification:
    return llm.structured(QueryClassification, CLASSIFY_PROMPT.format(
        domain=domain, jurisdiction=jurisdiction, question=question), purpose="kb_query_classification")


def ground_answer(question: str, *, domain: str, jurisdiction: str, asked_by: str,
                  project_id: int | None = None, as_of: date | None = None) -> dict:
    """Full step-6 pipeline for a stakeholder question. Low-confidence answers go to the review queue."""
    cls = classify_query(question, domain, jurisdiction)                                   # 1. classify
    hits: list[Hit] = []
    if cls.intent != "out_of_scope" and cls.collections:
        hits = search(cls.search_queries or [question], agent="kb_explorer", collections=list(cls.collections),
                      domain=domain, jurisdiction=jurisdiction, as_of=as_of, k=6)            # 2. retrieve
    by_ref = {h.ref: h for h in hits}
    if hits:
        answer = llm.structured(GroundedAnswer, ANSWER_PROMPT.format(                      # 3-4. evidence → generate
            domain=domain, jurisdiction=jurisdiction, evidence=evidence_block(hits), question=question))
    else:
        answer = GroundedAnswer(answer="No approved source in the knowledge base answers this question.",
                                claims=[], insufficient_evidence=True, confidence=0.0)
    claims, coverage = verify_claims(answer, by_ref)                                         # 5. citations
    cited_refs = sorted({r for c in claims for r in c["refs"]})
    strength = best_strength(cited_refs, by_ref)
    confidence = answer_confidence(answer.confidence, coverage, strength, answer.insufficient_evidence)

    reasons = []                                                                            # 6. escalate
    if answer.insufficient_evidence or not hits:
        reasons.append("insufficient evidence in approved sources")
    if claims and coverage < 1.0:
        reasons.append(f"{sum(not c['refs'] for c in claims)} claim(s) without a valid citation")
    if any(c["invalid_refs"] for c in claims):
        reasons.append("cited passages that were not retrieved (possible hallucination)")
    if confidence < get_settings().grounding_confidence_threshold:
        reasons.append(f"confidence {confidence:.2f} below {get_settings().grounding_confidence_threshold}")

    result = {
        "question": question, "classification": cls.model_dump(), "answer": answer.answer, "claims": claims,
        "citations": [{"ref": r, "citation": by_ref[r].citation, "strength": by_ref[r].strength, "issuer": by_ref[r].issuer,
                       "version": by_ref[r].version, "effective_from": by_ref[r].effective_from} for r in cited_refs],
        "evidence": [{k: v for k, v in h.to_dict().items() if k != "context"} for h in hits],
        "confidence": confidence, "components": {"llm": answer.confidence, "citation_coverage": round(coverage, 2),
                                                 "evidence_strength": strength},
        "escalated": bool(reasons), "escalation_reasons": reasons, "review_id": None,
    }
    if reasons:
        with SessionLocal.begin() as session:
            item = ReviewItem(project_id=project_id, kind="grounded_answer", subject=question, payload=result,
                              reasons=reasons, requested_by=asked_by)
            session.add(item)
            session.flush()
            result["review_id"] = item.id
    record(project_id, asked_by, "grounded_answer", {
        "question": question, "intent": cls.intent, "refs": cited_refs, "confidence": confidence,
        "escalated": bool(reasons), "review_id": result["review_id"]})
    return result
