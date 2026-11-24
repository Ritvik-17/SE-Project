"""Stakeholder-interaction agent: an adaptive requirements interview with one stakeholder (step 7).

    plan_question ──ask──> ask_stakeholder ──answer──> assess_answer ──> plan_question ...
          └──────finish──────────────────────────────────────────────> save_transcript

* The topics come from the 13-topic catalog (interview_topics.yaml), filtered and prioritised for the role.
* Each answer is assessed: the LLM judges it (complete, incomplete, vague, inconsistent, unknown, off-topic),
  lists the checklist points it answered and the facts it states, and deterministic checks
  (interview_policy.py) overrule it where they can: a figure is required for quantified points, and vague
  words without a figure count as vague.
* The policy then decides on a follow-up (up to INTERVIEW_MAX_FOLLOW_UPS per topic) or moves on to the next
  uncovered topic, skipping points already answered in passing. Gaps become open questions.
* The transcript, coverage, open questions and contradictions are saved as an `interview_transcript` source.
"""

from langgraph.types import interrupt

from app import llm
from app.agents import interview_policy as policy
from app.agents.common import domain_name
from app.audit import record
from app.catalog.loader import get_catalog, interview_plan
from app.config import get_settings
from app.graph.state import InterviewState
from app.ingestion.service import ingest
from app.schemas import AnswerAssessment, InterviewQuestion

QUESTION_PROMPT = """You are interviewing a stakeholder ({role}) to gather requirements for a {domain} system at a bank.

{task}

Facts the stakeholder has already stated:
{facts}

Recent conversation:
{recent}

Write ONE question: short (at most 35 words), neutral, and in plain language. Build on what the stakeholder already
said when it helps. Never ask again for something already answered. Never ask for personal data (names, account,
card or ID numbers)."""

NEW_TOPIC_TASK = """Pick the next topic from this list and write its opening question. Ask only for the missing points.
Prefer the topic that follows most naturally from the last answer.
{candidates}"""

FOLLOW_UP_TASKS = {
    "vague": "The last answer about {topic} was vague: it used {phrases} where a specific figure, limit, period or "
             "named standard is needed. Ask for the specific value.",
    "incomplete": "The last answer about {topic} left these points open: {missing}. Ask for them.",
    "inconsistent": "The last answer about {topic} conflicts with something said earlier: {contradiction}. Point this "
                    "out neutrally and ask which is correct, or under what conditions each applies.",
    "off_topic": "The last answer did not address {topic}. Steer back to it, asking about: {missing}.",
}

ASSESS_PROMPT = """You assess one stakeholder answer in a requirements interview for a {domain} system at a bank.

Current topic: {topic}. The points it needs (id: description; * = needs a number, amount, period, date or named standard):
{slots}

Points of other open topics the answer may also cover (topic_id.slot_id: description):
{other_slots}

Facts the stakeholder stated earlier (turn: fact):
{facts}

Turn {turn}. Question: {question}
<answer>{answer}</answer>

Set quality to:
- complete: specifically answers what was asked
- incomplete: answers only part of it
- vague: uses unmeasurable words (fast, secure, user-friendly, as needed, soon...) where a figure or specific rule is
  needed; list those words in vague_phrases
- inconsistent: contradicts an earlier fact; explain in contradiction and give its turn in contradicts_turn
- unknown: the stakeholder does not know or says it is another team's area; set refer_to_role to one of: {roles}
- off_topic: does not address the question
slots_answered: ids of the current topic's points answered specifically (a * point counts only with a concrete value).
other_slots: points of other topics that the answer also settles.
facts: each specific fact stated, as a short standalone sentence (at most 6)."""


def _plan(state: InterviewState) -> list[dict]:
    return interview_plan(state["role"], state["domain"])


def _role_name(state: InterviewState) -> str:
    return get_catalog().role(state["role"]).name


def _facts(state: InterviewState) -> str:
    return "\n".join(f"{f['turn']}: {f['fact']}" for f in state.get("facts", [])) or "(none yet)"


def _recent(state: InterviewState, n: int = 4) -> str:
    return "\n".join(f"Q{t['turn']}: {t['question']}\nA{t['turn']}: {t['answer'] or '(skipped)'}"
                     for t in state.get("transcript", [])[-n:]) or "(interview not started)"


def _finish(reason: str) -> dict:
    return {"next_turn": {"action": "finish", "topic": "", "question": "", "is_follow_up": False, "reason": reason}}


def plan_question(state: InterviewState) -> InterviewState:
    plan = _plan(state)
    coverage = state.get("coverage") or policy.init_coverage(plan)
    update: InterviewState = {"coverage": coverage}
    if len(state.get("transcript", [])) >= get_settings().interview_max_turns:
        return update | _finish("Turn limit reached")

    follow_up = state.get("pending_follow_up")
    if follow_up:
        topic = policy.topic_by_id(plan, follow_up["topic"])
        missing = "; ".join(s["label"] for s in follow_up["missing"]) or "the open points"
        task = FOLLOW_UP_TASKS[follow_up["kind"]].format(
            topic=topic["name"], missing=missing, contradiction=follow_up.get("contradiction", ""),
            phrases=", ".join(f'"{p}"' for p in follow_up.get("vague_phrases", [])) or "general terms")
        allowed = [topic]
    else:
        allowed = policy.next_topics(plan, coverage)
        if not allowed:
            return update | _finish("All topics for this role are covered")
        task = NEW_TOPIC_TASK.format(candidates="\n".join(
            f"- {t['id']} ({t['name']}, {t['priority']}). Missing: "
            + "; ".join(s["label"] for s in policy.missing_slots(t, coverage))
            + (f". Suggested wording: {' | '.join(t['suggested_questions'][:2])}" if t["suggested_questions"] else "")
            for t in allowed))

    q = llm.structured(InterviewQuestion, QUESTION_PROMPT.format(
        role=_role_name(state), domain=domain_name(state["domain"]), task=task, facts=_facts(state),
        recent=_recent(state)))
    topic = next((t for t in allowed if t["id"] == q.topic), allowed[0])  # the LLM may only choose an allowed topic
    question = q.question.strip() or (topic["opening"] if not follow_up else f"Could you be more specific about {topic['name'].lower()}?")
    if coverage[topic["id"]]["status"] == "pending":
        coverage = {**coverage, topic["id"]: {**coverage[topic["id"]], "status": "in_progress"}}
    return {"coverage": coverage, "next_turn": {
        "action": "ask", "topic": topic["id"], "topic_name": topic["name"], "category": topic["categories"][0],
        "question": question, "is_follow_up": bool(follow_up), "follow_up_kind": follow_up["kind"] if follow_up else None,
        "reason": q.reason, "missing": [s["label"] for s in policy.missing_slots(topic, coverage)]}}


def ask_stakeholder(state: InterviewState) -> InterviewState:
    turn = state["next_turn"]
    number = len(state.get("transcript", [])) + 1
    reply = interrupt({k: turn.get(k) for k in ("question", "topic", "topic_name", "category", "is_follow_up",
                                                "follow_up_kind", "reason", "missing")} | {"turn": number})
    entry = {"turn": number, "topic": turn["topic"], "topic_name": turn["topic_name"], "category": turn["category"],
             "question": turn["question"], "is_follow_up": turn["is_follow_up"],
             "follow_up_kind": turn.get("follow_up_kind"), "answer": reply.get("answer", "")}
    update: InterviewState = {"transcript": [*state.get("transcript", []), entry]}
    if reply.get("finish"):
        update["next_turn"] = turn | {"action": "finish", "reason": "Stakeholder ended the interview"}
    return update


def assess_answer(state: InterviewState) -> InterviewState:
    plan = _plan(state)
    coverage = state["coverage"]
    entry = state["transcript"][-1]
    topic = policy.topic_by_id(plan, entry["topic"])
    assessment: dict = {}
    if entry["answer"].strip():
        others = [f"{t['id']}.{s['id']}: {s['label']}" for t in plan if t["id"] != topic["id"]
                  and coverage[t["id"]]["status"] in ("pending", "in_progress") for s in policy.missing_slots(t, coverage)]
        assessment = llm.structured(AnswerAssessment, ASSESS_PROMPT.format(
            domain=domain_name(state["domain"]), topic=topic["name"],
            slots="\n".join(f"- {s['id']}{'*' if s.get('quantified') else ''}: {s['label']}" for s in topic["slots"]),
            other_slots="\n".join(others) or "(none)", facts=_facts(state), turn=entry["turn"],
            question=entry["question"], answer=entry["answer"],
            roles=", ".join(r.id for r in get_catalog().roles))).model_dump()

    result = policy.evaluate_answer(plan, coverage, topic["id"], entry["turn"], entry["answer"], assessment,
                                    state["role"], get_settings().interview_max_follow_ups,
                                    state.get("pending_follow_up"))
    contradictions = list(state.get("contradictions", []))
    if result["resolved_contradiction"] and contradictions:
        contradictions[-1] = {**contradictions[-1], "resolved": True, "resolved_turn": entry["turn"]}
    if result["contradiction"]:
        contradictions.append(result["contradiction"])
    entry = entry | {"assessment": {"quality": result["quality"], "vague_phrases": result["vague_phrases"],
                                    "missing": result["missing"], "note": assessment.get("note", ""),
                                    "follow_up": result["follow_up"]["kind"] if result["follow_up"] else None}}
    facts = [*state.get("facts", []), *({"turn": entry["turn"], "topic": topic["id"], "fact": f}
                                        for f in assessment.get("facts", [])[:6])]
    return {"coverage": result["coverage"], "pending_follow_up": result["follow_up"], "facts": facts,
            "contradictions": contradictions, "transcript": [*state["transcript"][:-1], entry],
            "open_questions": [*state.get("open_questions", []), *result["open_questions"]]}


def route_interview(state: InterviewState) -> str:
    return "save_transcript" if state["next_turn"]["action"] == "finish" else "ask_stakeholder"


def route_after_answer(state: InterviewState) -> str:
    return "save_transcript" if state["next_turn"]["action"] == "finish" else "assess_answer"


def save_transcript(state: InterviewState) -> InterviewState:
    answered = [t for t in state.get("transcript", []) if t["answer"].strip()]
    plan = _plan(state)
    coverage = state.get("coverage") or policy.init_coverage(plan)
    summary = policy.coverage_summary(plan, coverage)
    if not answered:
        record(state["project_id"], "stakeholder_interaction_agent", "interview_discarded", {"role": state["role"]})
        return {"source_id": None}

    role = _role_name(state)
    lines = [f"Adaptive interview with: {role}", ""]
    for t in answered:
        tag = f" (follow-up: {t['follow_up_kind']})" if t["is_follow_up"] else ""
        lines += [f"[{t.get('topic_name', t['category'])}]{tag} Q: {t['question']}", f"A: {t['answer']}", ""]
    lines += ["Topic coverage:"]
    lines += [f"- {t['name']}: {coverage[t['id']]['status']}" for t in plan]
    # Open points and unresolved contradictions are listed so the clarification agent can route them.
    still_open = [q for q in state.get("open_questions", [])
                  if q["slot"] not in coverage[q["topic"]]["answered"]]
    if still_open:
        lines += ["", "Open points this stakeholder could not settle (to be clarified):"]
        lines += [f"- {q['question']}" + (f" Refer to: {q['target_role']}." if q["target_role"] else "") for q in still_open]
    unresolved = [c for c in state.get("contradictions", []) if not c.get("resolved")]
    if unresolved:
        lines += ["", "Inconsistencies not resolved during the interview:"]
        lines += [f"- Turn {c['turn']} vs turn {c['earlier_turn']}: {c['explanation']}" for c in unresolved]

    source = ingest(state["project_id"], "interview_transcript", f"AI interview — {role}", "\n".join(lines),
                    state["role"], actor="stakeholder_interaction_agent")
    record(state["project_id"], "stakeholder_interaction_agent", "interview_completed",
           {"role": state["role"], "turns": len(state["transcript"]), "answered": len(answered),
            "follow_ups": sum(t["is_follow_up"] for t in answered), "coverage": summary,
            "open_questions": len(still_open), "contradictions": len(state.get("contradictions", [])),
            "unresolved_contradictions": len(unresolved), "source_id": source.id})
    return {"source_id": source.id}
