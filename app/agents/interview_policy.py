"""Deterministic interview policy: topic coverage, answer checks and the follow-up decision.

The LLM assesses each answer and words each question; this module decides what happens next, so the interview's
behaviour (when to probe, when to move on, when to stop) is predictable, testable and auditable.
"""

import re

VAGUE_TERMS = [
    "fast", "quick", "quickly", "slow", "speedy", "instant", "instantly", "secure", "securely", "safe", "robust",
    "scalable", "reliable", "highly available", "always available", "user-friendly", "user friendly", "easy", "simple",
    "intuitive", "seamless", "high", "low", "large", "small", "many", "few", "several", "a lot", "lots",
    "enough", "adequate", "appropriate", "reasonable", "sufficient", "minimal", "as needed", "as required",
    "when needed", "asap", "soon", "regularly", "periodically", "frequently", "industry standard",
    "best practice", "best practices", "etc", "and so on", "as per policy",
]
_VAGUE_RE = re.compile(r"\b(" + "|".join(re.escape(t) for t in sorted(VAGUE_TERMS, key=len, reverse=True)) + r")\b", re.I)
_QUANTITY_RE = re.compile(
    r"\d|\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|fifty|hundred|"
    r"thousand|lakh|lakhs|crore|crores|million|billion|half|daily|weekly|monthly|quarterly|annually|yearly|"
    r"january|february|march|april|may|june|july|august|september|october|november|december)\b", re.I)
_UNKNOWN_RE = re.compile(r"\b(don'?t know|do not know|not sure|no idea|unsure|not my (area|team|department|call)|"
                         r"tbd|to be decided|can'?t say|cannot say|ask (the|our) )", re.I)

QUALITIES = ("complete", "incomplete", "vague", "inconsistent", "unknown", "off_topic")
FOLLOW_UP_ORDER = ("inconsistent", "vague", "off_topic", "incomplete")  # which problem to probe first


def vague_phrases(text: str) -> list[str]:
    return list(dict.fromkeys(m.group(0).lower() for m in _VAGUE_RE.finditer(text or "")))


def has_quantity(text: str) -> bool:
    return bool(_QUANTITY_RE.search(text or ""))


def looks_unknown(text: str) -> bool:
    return bool(_UNKNOWN_RE.search(text or ""))


def init_coverage(plan: list[dict]) -> dict:
    return {t["id"]: {"status": "pending", "answered": [], "follow_ups": 0, "turns": [], "in_passing": []}
            for t in plan}


def topic_by_id(plan: list[dict], topic_id: str) -> dict | None:
    return next((t for t in plan if t["id"] == topic_id), None)


def missing_slots(topic: dict, coverage: dict) -> list[dict]:
    done = set(coverage[topic["id"]]["answered"])
    return [s for s in topic["slots"] if s["id"] not in done]


def next_topics(plan: list[dict], coverage: dict, limit: int = 4) -> list[dict]:
    """Topics not yet started, primary tier first. The LLM may choose among them so the conversation flows."""
    pending = [t for t in plan if coverage[t["id"]]["status"] == "pending"]
    tier = [t for t in pending if t["priority"] == "primary"] or pending
    return tier[:limit]


def evaluate_answer(plan: list[dict], coverage: dict, topic_id: str, turn: int, answer: str, assessment: dict,
                    current_role: str, max_follow_ups: int, pending_follow_up: dict | None) -> dict:
    """Merge the LLM's assessment with deterministic checks and decide whether to follow up.

    Returns {"coverage", "quality", "vague_phrases", "missing", "follow_up", "open_questions", "contradiction",
    "resolved_contradiction"}. Coverage is copied, never mutated in place (LangGraph state).
    """
    coverage = {k: {**v, "answered": list(v["answered"]), "turns": list(v["turns"]), "in_passing": list(v["in_passing"])}
                for k, v in coverage.items()}
    topic = topic_by_id(plan, topic_id)
    cov = coverage[topic_id]
    cov["turns"].append(turn)
    out = {"coverage": coverage, "vague_phrases": [], "missing": [], "follow_up": None, "open_questions": [],
           "contradiction": None, "resolved_contradiction": False}

    if not (answer or "").strip():  # the stakeholder skipped: no probing, the gaps go to the open-question list
        cov["status"] = "skipped"
        out["quality"] = "skipped"
        out["missing"] = [s["id"] for s in missing_slots(topic, coverage)]
        out["open_questions"] = _open_questions(topic, out["missing"], current_role, "", "skipped by stakeholder")
        return out

    quality = assessment.get("quality") if assessment.get("quality") in QUALITIES else "incomplete"
    quantified = {s["id"] for s in topic["slots"] if s.get("quantified")}
    numeric = has_quantity(answer)

    # Slots for this topic. A slot that needs a figure only counts if the answer contains one.
    slot_ids = {s["id"] for s in topic["slots"]}
    claimed = [s for s in assessment.get("slots_answered", []) if s in slot_ids]
    rejected = [s for s in claimed if s in quantified and not numeric]
    for s in claimed:
        if s not in rejected and s not in cov["answered"]:
            cov["answered"].append(s)

    # Slots for other topics answered in passing, so the interviewer will not ask for them again.
    for ref in assessment.get("other_slots", []):
        other_id, _, slot = ref.partition(".")
        other = topic_by_id(plan, other_id)
        other_slot = next((s for s in other["slots"] if s["id"] == slot), None) if other else None
        if other_slot and other_id != topic_id and (numeric or not other_slot.get("quantified")):
            oc = coverage[other_id]
            if slot not in oc["answered"]:
                oc["answered"].append(slot)
                oc["in_passing"].append(slot)
            if oc["status"] == "pending" and not missing_slots(other, coverage):
                oc["status"] = "covered"

    # Deterministic checks the LLM cannot talk its way out of.
    open_quantified = [s for s in missing_slots(topic, coverage) if s["id"] in quantified]
    phrases = list(dict.fromkeys([*(p.lower() for p in assessment.get("vague_phrases", [])), *vague_phrases(answer)]))
    if phrases and open_quantified and not numeric and quality in ("complete", "incomplete"):
        quality = "vague"
    if rejected and quality in ("complete", "incomplete"):
        quality = "vague"
        phrases = phrases or ["no figure given"]
    if looks_unknown(answer) and not claimed and quality not in ("inconsistent",):
        quality = "unknown"
    out["vague_phrases"] = phrases if quality == "vague" else []

    missing = [s["id"] for s in missing_slots(topic, coverage)]
    out["missing"] = missing
    if quality == "complete" and missing:
        quality = "incomplete"
    out["quality"] = quality

    if quality == "inconsistent":
        out["contradiction"] = {"turn": turn, "topic": topic_id, "earlier_turn": assessment.get("contradicts_turn"),
                                "explanation": assessment.get("contradiction", "") or "Conflicts with an earlier answer",
                                "resolved": False}
    elif pending_follow_up and pending_follow_up.get("kind") == "inconsistent":
        out["resolved_contradiction"] = True  # the follow-up answer no longer contradicts

    if quality == "unknown":
        cov["status"] = "partial" if cov["answered"] else "skipped"
        out["open_questions"] = _open_questions(topic, missing, current_role, assessment.get("refer_to_role", ""),
                                                "stakeholder did not know")
        return out

    needs = quality if quality in FOLLOW_UP_ORDER else ("incomplete" if missing else None)
    if needs and cov["follow_ups"] < max_follow_ups:
        cov["status"] = "in_progress"
        cov["follow_ups"] += 1
        out["follow_up"] = {"topic": topic_id, "kind": needs, "vague_phrases": out["vague_phrases"],
                            "missing": [s for s in topic["slots"] if s["id"] in missing],
                            "contradiction": (out["contradiction"] or {}).get("explanation", "")}
        return out

    cov["status"] = "partial" if missing else "covered"
    if missing:
        out["open_questions"] = _open_questions(topic, missing, current_role, assessment.get("refer_to_role", ""),
                                                "follow-up limit reached")
    return out


def _open_questions(topic: dict, missing: list[str], current_role: str, refer_to: str,
                    reason: str) -> list[dict]:
    """Unanswered slots become open questions, routed to the role named by the stakeholder, if any."""
    labels = {s["id"]: s["label"] for s in topic["slots"]}
    return [{"topic": topic["id"], "slot": s, "question": f"{topic['name']}: {labels[s]}?",
             "target_role": refer_to if refer_to and refer_to != current_role else None, "reason": reason}
            for s in missing]


def interview_complete(plan: list[dict], coverage: dict) -> bool:
    return not any(coverage[t["id"]]["status"] in ("pending", "in_progress") for t in plan)


def coverage_summary(plan: list[dict], coverage: dict) -> dict:
    counts: dict[str, int] = {}
    for t in plan:
        counts[coverage[t["id"]]["status"]] = counts.get(coverage[t["id"]]["status"], 0) + 1
    slots = sum(len(t["slots"]) for t in plan)
    answered = sum(len(coverage[t["id"]]["answered"]) for t in plan)
    primary = [t for t in plan if t["priority"] == "primary"]
    primary_done = sum(coverage[t["id"]]["status"] == "covered" for t in primary)
    return {"topics": len(plan), "by_status": counts, "slot_coverage": round(answered / slots, 2) if slots else 1.0,
            "primary_covered": f"{primary_done}/{len(primary)}"}
