"""Evaluation metrics (problem statement step 19). Deterministic: no LLM is used to grade the LLM.

Requirement matching: gold and predicted statements are embedded with the local model (bge-small, free) and matched
one-to-one greedily by cosine similarity >= threshold (default 0.80). The report also gives results at 0.75 and 0.85
so the sensitivity to the threshold is visible, and `adjudications` in a report can override individual matches.
"""

import re
from statistics import mean

from app.agents.standards import REQUIREMENT_FIELDS, quote_in_source

AMBIGUITY_CHECKS = {"ambiguity"}
TRACE_LINKS = ("stakeholder_source", "verified_quote", "acceptance_tests", "regulation_or_citation", "design_artefact",
               "sdlc_phase")


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3), "tp": tp, "fp": fp, "fn": fn}


# ---------- Matching ----------

def similarity_matrix(gold: list[str], predicted: list[str]) -> list[list[float]]:
    from app import llm
    if not gold or not predicted:
        return [[0.0] * len(predicted) for _ in gold]
    g, p = llm.embed_many(gold), llm.embed_many(predicted)
    return [[round(sum(a * b for a, b in zip(gv, pv)), 4) for pv in p] for gv in g]


def match(sim: list[list[float]], threshold: float) -> dict[int, tuple[int, float]]:
    """Greedy one-to-one matching: {gold index: (predicted index, similarity)}."""
    pairs = sorted(((s, gi, pi) for gi, row in enumerate(sim) for pi, s in enumerate(row) if s >= threshold), reverse=True)
    used_g, used_p, out = set(), set(), {}
    for s, gi, pi in pairs:
        if gi not in used_g and pi not in used_p:
            out[gi] = (pi, s)
            used_g.add(gi)
            used_p.add(pi)
    return out


# ---------- 1. Extraction precision / recall / F1 ----------

def extraction_scores(gold: list[dict], predicted: list[dict], sim, threshold: float) -> dict:
    m = match(sim, threshold)
    out = prf(len(m), len(predicted) - len(m), len(gold) - len(m))
    out["threshold"] = threshold
    return out


# ---------- 2. Completeness ----------

def completeness(gold: list[dict], m: dict, baseline: list[dict], mandatory_categories: list[str]) -> dict:
    must = [i for i, g in enumerate(gold) if g.get("must")]
    must_recall = sum(i in m for i in must) / len(must) if must else 1.0
    cats = {c for r in baseline for c in r.get("categories", [])}
    category_coverage = sum(c in cats for c in mandatory_categories) / len(mandatory_categories) if mandatory_categories else 1.0
    fields = [k for k, _ in REQUIREMENT_FIELDS]

    def filled(r: dict) -> float:
        rec = {"id": r.get("id"), "statement": r.get("statement"), "categories": r.get("categories"),
               "source_stakeholder": r.get("stakeholder_role") or r.get("origin"),
               "business_justification": r.get("business_justification"), "priority": r.get("priority"),
               "dependencies": [*r.get("depends_on", []), *r.get("dependencies", [])] or None,
               "assumptions": r.get("assumptions") or None, "acceptance_criteria": r.get("acceptance_criteria"),
               "applicable_regulations": r.get("applicable_regulations") or None, "risk_level": r.get("risk_level"),
               "confidence": r.get("confidence"), "approval_status": r.get("status")}
        # dependencies, assumptions and regulations may legitimately be empty; count them as filled when present
        required = [f for f in fields if f not in ("dependencies", "assumptions", "applicable_regulations")]
        return sum(bool(rec[f]) for f in required) / len(required)
    field_completeness = mean(filled(r) for r in baseline) if baseline else 0.0
    return {"must_have_recall": round(must_recall, 3), "mandatory_category_coverage": round(category_coverage, 3),
            "record_field_completeness": round(field_completeness, 3),
            "score": round(mean([must_recall, category_coverage, field_completeness]), 3),
            "missing_must_have": [gold[i]["id"] for i in must if i not in m]}


# ---------- 3. Ambiguity detection ----------

def ambiguity_detection(gold: list[dict], predicted: list[dict], m: dict, issues: list[dict], clarifications: list[dict]) -> dict:
    flagged = {i["req_id"] for i in issues if i.get("check") in AMBIGUITY_CHECKS and i.get("req_id")}
    asked = {rid for q in clarifications for rid in q.get("related_req_ids", [])}
    tp = fp = fn = tn = 0
    rows = []
    for gi, (pi, _) in m.items():
        rid = predicted[pi]["id"]
        predicted_amb = rid in flagged or (rid in asked and bool(re.search(r"vague|ambigu|measurable|specific", " ".join(
            q["question"] + q.get("reason", "") for q in clarifications if rid in q.get("related_req_ids", [])), re.I)))
        truth = bool(gold[gi].get("ambiguous"))
        tp += truth and predicted_amb
        fp += (not truth) and predicted_amb
        fn += truth and not predicted_amb
        tn += (not truth) and not predicted_amb
        if truth or predicted_amb:
            rows.append({"gold": gold[gi]["id"], "requirement": rid, "gold_ambiguous": truth, "flagged": predicted_amb})
    total = tp + fp + fn + tn
    out = prf(tp, fp, fn) | {"accuracy": round((tp + tn) / total, 3) if total else 0.0, "evaluated": total, "rows": rows}
    out["unmatched_ambiguous_gold"] = [g["id"] for i, g in enumerate(gold) if g.get("ambiguous") and i not in m]
    return out


# ---------- 4. Conflict detection ----------

def conflict_detection(gold: list[dict], gold_conflicts: list[dict], predicted: list[dict], m: dict,
                       conflicts: list[dict]) -> dict:
    pred_to_gold = {predicted[pi]["id"]: gold[gi]["id"] for gi, (pi, _) in m.items()}
    truth = {frozenset(c["pair"]) for c in gold_conflicts}
    found = set()
    for c in conflicts:
        if c.get("kind") != "conflict":
            continue
        ids = [pred_to_gold.get(r) for r in c["req_ids"]]
        ids = [i for i in ids if i]
        for a in ids:
            for b in ids:
                if a < b:
                    found.add(frozenset((a, b)))
    tp = len(truth & found)
    out = prf(tp, len(found - truth), len(truth - found))
    out["detected"] = sorted(sorted(p) for p in truth & found)
    out["missed"] = sorted(sorted(p) for p in truth - found)
    return out


def policy_contradictions(gold: list[dict], predicted: list[dict], m: dict, contradictions: list[dict]) -> dict:
    by_gold = {gold[gi]["id"]: predicted[pi] for gi, (pi, _) in m.items()}
    hits = [c["id"] for c in contradictions if by_gold.get(c["id"], {}).get("grounding_support") == "contradicts_evidence"]
    return {"detected": hits, "expected": [c["id"] for c in contradictions],
            "recall": round(len(hits) / len(contradictions), 3) if contradictions else 1.0}


# ---------- 5. Regulatory-control coverage ----------

def control_coverage(controls: list[dict], texts: list[str], threshold: float = 0.75) -> dict:
    from app import llm
    low = [t.lower() for t in texts]
    covered, missing = [], []
    vecs = llm.embed_many(texts) if texts else []
    for c in controls:
        by_kw = any(all(k.lower() in t for k in group) for group in c["keywords"] for t in low)
        by_sim = False
        if not by_kw and vecs:
            cv = llm.embed_many([c["description"]])[0]
            by_sim = max(sum(a * b for a, b in zip(cv, v)) for v in vecs) >= threshold
        (covered if by_kw or by_sim else missing).append(c["id"])
    return {"coverage": round(len(covered) / len(controls), 3) if controls else 1.0, "covered": covered, "missing": missing}


# ---------- 6. Hallucination rate, 7. Citation correctness ----------

def hallucination(predicted: list[dict], source_text: dict[int, str], grounding: dict, compliance: dict) -> dict:
    quotes = [r for r in predicted if r.get("source_id") in source_text]
    unsupported = [r["id"] for r in quotes
                   if quote_in_source(r.get("source_quote", ""), source_text[r["source_id"]]) == "not_found"]
    proposed_refs = sum(len(g.get("citations", [])) + len(g.get("dropped_refs", [])) for g in grounding.values())
    invented_refs = sum(len(g.get("dropped_refs", [])) for g in grounding.values())
    mappings = compliance.get("mappings", [])
    claims = len(quotes) + proposed_refs
    bad = len(unsupported) + invented_refs
    return {"rate": round(bad / claims, 3) if claims else 0.0, "unsupported_quotes": unsupported,
            "unsupported_quote_rate": round(len(unsupported) / len(quotes), 3) if quotes else 0.0,
            "invented_citation_rate": round(invented_refs / proposed_refs, 3) if proposed_refs else 0.0,
            "invented_citations_removed": invented_refs, "claims_checked": claims,
            "compliance_mappings_without_evidence": sum(m.get("evidence_ref") in ("none", "catalog") for m in mappings)}


def citation_correctness(gold: list[dict], predicted: list[dict], m: dict, compliance: dict) -> dict:
    by_pred = {predicted[pi]["id"]: gold[gi] for gi, (pi, _) in m.items()}
    correct = wrong = unverifiable = 0
    rows = []
    for r in predicted:
        g = by_pred.get(r["id"])
        for c in r.get("citations", []):
            expected = (g or {}).get("expected_kb")
            if not expected:
                unverifiable += 1
                continue
            ok = c.get("doc_key") in expected
            correct += ok
            wrong += not ok
            rows.append({"requirement": r["id"], "gold": g["id"], "cited": c.get("doc_key"), "expected": expected, "correct": ok})
    checked = correct + wrong
    return {"correctness": round(correct / checked, 3) if checked else None, "checked": checked, "correct": correct,
            "wrong": wrong, "unverifiable": unverifiable, "rows": rows,
            "verified_against_retrieval": 1.0}  # refs not retrieved are removed before output (see hallucination)


# ---------- 8. SDLC ----------

def sdlc_accuracy(ranking: list[dict], expert_choices: list[str]) -> dict:
    ids = [r["model_id"] for r in ranking]
    if not expert_choices:
        return {"status": "no expert label"}
    majority = max(set(expert_choices), key=expert_choices.count)
    rank = ids.index(majority) + 1 if majority in ids else None
    return {"engine_top1": ids[0], "expert_majority": majority, "top1_match": ids[0] == majority,
            "top3_hit": majority in ids[:3], "expert_rank_in_engine": rank,
            "reciprocal_rank": round(1 / rank, 3) if rank else 0.0, "experts": len(expert_choices)}


# ---------- 9. Human correction rate ----------

def human_correction(requirements: list[dict], compliance: dict, sdlc_approvals: list[dict], workflow: dict) -> dict:
    ai = [r for r in requirements if r.get("origin", "extracted") == "extracted"]
    decided = [r for r in ai if r.get("status") in ("accepted", "modified", "rejected")]
    corrected = [r for r in ai if r.get("status") in ("modified", "rejected")]
    interp = [m for m in compliance.get("mappings", []) if m.get("legal_decision")]
    interp_corrected = [m for m in interp if m["legal_decision"]["action"] in ("modify", "reject")]
    override = any(a.get("override") for a in sdlc_approvals)
    edits = len(workflow.get("human_edits", []))
    denominator = len(ai) + len(interp) + 1
    return {"rate": round((len(corrected) + len(interp_corrected) + override) / denominator, 3),
            "requirements_corrected": len(corrected), "requirements_total": len(ai), "requirements_explicitly_decided": len(decided),
            "interpretations_corrected": len(interp_corrected), "interpretations_decided": len(interp),
            "sdlc_override": override, "workflow_edits": edits}


# ---------- 10. Time saved ----------

def time_saved(audit: list[dict], manual_hours: float | None, human_actors: set[str]) -> dict:
    """AI time = from each start or human decision to the last agent event before the next human decision;
    human time = from that agent event to the decision."""
    from datetime import datetime
    events = sorted(audit, key=lambda e: e["at"])
    ai_s = human_s = 0.0
    last_agent = segment_start = None
    for e in events:
        t = datetime.fromisoformat(e["at"])
        is_human = e.get("principal") in human_actors and e["action"].split("_")[0] in (
            "baseline", "sdlc", "workflow", "clarification", "clarifications", "legal")
        if segment_start is None:
            segment_start = t
        if is_human:
            if last_agent is not None:
                ai_s += (last_agent - segment_start).total_seconds()
                human_s += (t - last_agent).total_seconds()
            segment_start, last_agent = t, None
        else:
            last_agent = t
    if last_agent is not None and segment_start is not None:
        ai_s += (last_agent - segment_start).total_seconds()
    total_h = (ai_s + human_s) / 3600
    out = {"ai_processing_minutes": round(ai_s / 60, 1), "human_review_minutes": round(human_s / 60, 1),
           "assisted_total_hours": round(total_h, 2), "manual_hours": manual_hours}
    out["time_saved_pct"] = round(100 * (1 - total_h / manual_hours), 1) if manual_hours else None
    return out


# ---------- 11. Stakeholder satisfaction ----------

def sus_score(answers: list[int]) -> float:
    """System Usability Scale (10 items, 1-5): odd items positive, even items negative; result 0-100."""
    return (sum(a - 1 for a in answers[0::2]) + sum(5 - a for a in answers[1::2])) * 2.5


def satisfaction(feedback: list[dict]) -> dict:
    if not feedback:
        return {"status": "no responses yet", "responses": 0}
    sus = [sus_score(f["sus"]) for f in feedback if len(f.get("sus", [])) == 10]
    useful = [f["usefulness"] for f in feedback if f.get("usefulness")]
    trust = [f["trust"] for f in feedback if f.get("trust")]
    return {"responses": len(feedback), "sus_mean": round(mean(sus), 1) if sus else None,
            "usefulness_mean": round(mean(useful), 2) if useful else None, "trust_mean": round(mean(trust), 2) if trust else None,
            "by_role": {r: len([f for f in feedback if f.get("role") == r]) for r in {f.get("role") for f in feedback}}}


# ---------- 12. Traceability coverage ----------

def traceability(rtm: list[dict], requirements: list[dict], source_text: dict[int, str]) -> dict:
    by_id = {r["id"]: r for r in requirements}
    regulated = {"regulatory", "privacy", "security", "audit", "data"}
    counts = {k: 0 for k in TRACE_LINKS}
    full = 0
    for row in rtm:
        r = by_id.get(row["req_id"], {})
        links = {
            "stakeholder_source": bool(row.get("stakeholder_role") or row.get("origin") != "extracted"),
            "verified_quote": row.get("origin") != "extracted" or (
                r.get("source_id") in source_text and quote_in_source(r.get("source_quote", ""), source_text[r["source_id"]]) != "not_found"),
            "acceptance_tests": row.get("tests", 0) > 0,
            "regulation_or_citation": not (regulated & set(row.get("categories", []))) or bool(row.get("regulations") or row.get("citations")),
            "design_artefact": row.get("type") != "functional" or bool(row.get("use_cases") or row.get("user_story")),
            "sdlc_phase": bool(row.get("sdlc_phase")),
        }
        for k, v in links.items():
            counts[k] += v
        full += all(links.values())
    n = len(rtm) or 1
    return {"full_chain": round(full / n, 3), "by_link": {k: round(v / n, 3) for k, v in counts.items()}, "requirements": len(rtm)}
