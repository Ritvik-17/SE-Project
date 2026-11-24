"""Adaptive requirement-gathering interviews (step 7): topics, answer assessment and follow-ups."""

import re

import pytest
from fastapi.testclient import TestClient

from app import llm
from app.agents import interview_policy as policy
from app.api.main import app
from app.catalog.loader import get_catalog, interview_plan
from app.schemas import AnswerAssessment, InterviewQuestion

PROMPTS: list[str] = []


def _assess(answer: str) -> dict:
    if "fast" in answer:  # claims the volume point without a figure: the policy must reject it
        return {"quality": "complete", "slots_answered": ["user_groups", "accessibility", "volumes"],
                "other_slots": ["existing_workflow.tools"], "facts": ["Users are salaried customers and students"]}
    if "20000" in answer:
        return {"quality": "complete", "slots_answered": ["volumes", "tasks"], "facts": ["20000 customers a month"]}
    if "photocopies" in answer:
        return {"quality": "incomplete", "slots_answered": ["steps", "pain_points"], "facts": ["Onboarding takes 5 days"]}
    if "approve within 2 days" in answer:
        return {"quality": "inconsistent", "slots_answered": ["handoffs"], "contradicts_turn": 3,
                "contradiction": "Turn 3 said onboarding takes 5 days; now 2 days", "facts": ["Operations approve in 2 days"]}
    if "end to end" in answer:
        return {"quality": "complete", "slots_answered": [], "facts": ["5 days end to end; 2 days in operations"]}
    if "not sure" in answer:
        return {"quality": "unknown", "refer_to_role": "business_analyst"}
    return {"quality": "off_topic"}


def fake_structured(schema, prompt):
    PROMPTS.append(prompt)
    if schema is InterviewQuestion:
        if "The last answer" in prompt:
            kind = next(k for k in ("vague", "left these points open", "conflicts", "did not address") if k in prompt)
            return InterviewQuestion(topic="", question=f"Follow-up ({kind})?", reason=kind)
        first = re.search(r"^- (\w+) \(", prompt, re.M).group(1)
        return InterviewQuestion(topic=first, question=f"Tell me about {first}?", reason="next topic")
    if schema is AnswerAssessment:
        return AnswerAssessment.model_validate(_assess(re.search(r"<answer>(.*)</answer>", prompt, re.S).group(1)))
    raise AssertionError(schema)


@pytest.fixture
def client(monkeypatch):
    PROMPTS.clear()
    monkeypatch.setattr(llm, "call_model", fake_structured)
    with TestClient(app) as c:
        yield c


# ---------- Topic catalog ----------

def test_all_thirteen_topics_and_role_plans():
    topics = get_catalog().interview_topics
    assert len(topics) == 13 and not get_catalog().validate_references()
    assert {t.id for t in topics} >= {"transaction_limits", "authentication_authorisation", "schedule_budget"}
    plan = interview_plan("risk_management", "loan_processing")
    assert plan[0]["id"] == "transaction_limits" and plan[0]["priority"] == "primary"
    assert all(t["priority"] == "secondary" for t in plan[1:])
    assert "schedule_budget" not in {t["id"] for t in interview_plan("customer")}  # not asked of customers
    business = next(t for t in plan if t["id"] == "business_objectives")
    assert any("affordability" in q for q in business["suggested_questions"])  # domain question reused


# ---------- Deterministic policy ----------

def test_vagueness_and_quantity_checks():
    assert policy.vague_phrases("It must be fast and secure, as needed") == ["fast", "secure", "as needed"]
    assert policy.has_quantity("within 2 seconds") and policy.has_quantity("by March") and not policy.has_quantity("soon")
    assert policy.looks_unknown("Not sure, ask the risk team")


def test_policy_follow_up_budget_then_open_questions():
    plan = interview_plan("operations")
    cov = policy.init_coverage(plan)
    perf = "performance_availability"
    r = policy.evaluate_answer(plan, cov, perf, 1, "It should be fast and always available",
                               {"quality": "complete", "slots_answered": ["response_time", "uptime"]}, "operations", 1, None)
    assert r["quality"] == "vague" and r["follow_up"]["kind"] == "vague"
    assert r["coverage"][perf]["answered"] == [] and "fast" in r["vague_phrases"]  # no figure, no credit
    r = policy.evaluate_answer(plan, r["coverage"], perf, 2, "Under 2 seconds, 99.9% uptime",
                               {"quality": "complete", "slots_answered": ["response_time", "uptime"]}, "operations", 1,
                               r["follow_up"])
    assert r["follow_up"] is None and r["coverage"][perf]["status"] == "partial"  # budget of 1 used up
    assert {q["slot"] for q in r["open_questions"]} == {"volume", "recovery", "maintenance"}
    assert cov[perf]["answered"] == []  # input coverage was not mutated


# ---------- The interview graph through the API ----------

def test_adaptive_interview(client):
    pid = client.post("/projects", json={"name": "Interview", "domain": "kyc_onboarding"}).json()["id"]
    s = client.post(f"/projects/{pid}/interview-sessions", json={"stakeholder_role": "customer"}).json()
    sid = s["session_id"]
    assert s["question"]["topic"] == "users_roles" and not s["question"]["is_follow_up"]
    assert [t["priority"] for t in s["topics"][:2]] == ["primary", "primary"]

    def reply(answer, finish=False):
        return client.post(f"/projects/{pid}/interview-sessions/{sid}/reply", json={"answer": answer, "finish": finish}).json()

    # 1. Vague: "fast" with no figure. The volume point is not credited, and a follow-up asks for a figure.
    s = reply("Salaried customers and students, mostly on mobile. It should be fast. Mail a.b@bank.in")
    assert "a.b@bank.in" not in s["transcript"][0]["answer"]  # masked before the LLM sees it
    assert s["question"]["is_follow_up"] and s["question"]["follow_up_kind"] == "vague"
    assert s["transcript"][0]["assessment"]["quality"] == "vague"
    workflow = next(t for t in s["topics"] if t["id"] == "existing_workflow")
    assert any(sl["id"] == "tools" and sl["in_passing"] for sl in workflow["slots"])  # answered in passing

    # 2. Specific answer: the topic is covered, so the next topic starts.
    s = reply("About 20000 customers a month; they open an account and do video KYC")
    assert next(t for t in s["topics"] if t["id"] == "users_roles")["status"] == "covered"
    assert s["question"]["topic"] == "existing_workflow" and not s["question"]["is_follow_up"]
    assert "Systems or tools used today" not in s["question"]["missing"]  # not asked again

    # 3. Incomplete, 4. inconsistent, 5. resolved.
    s = reply("Today they visit a branch with photocopies; it takes 5 days")
    assert s["question"]["follow_up_kind"] == "incomplete"
    s = reply("Branch staff email documents to operations, who approve within 2 days")
    assert s["question"]["follow_up_kind"] == "inconsistent" and s["contradictions"][0]["earlier_turn"] == 3
    s = reply("5 days end to end; the 2 days is only the operations step")
    assert s["contradictions"][0]["resolved"] and not s["question"]["is_follow_up"]

    # 6. Skipped topic, 7. "don't know" routed to another role.
    s = reply("")
    assert next(t for t in s["topics"] if t["id"] == "business_objectives")["status"] == "skipped"
    s = reply("I'm not sure, ask the business analyst")
    assert any(q["target_role"] == "business_analyst" for q in s["open_questions"])
    assert not s["question"]["is_follow_up"]  # no probing after "don't know"

    s = reply("", finish=True)
    assert s["status"] == "completed" and s["source_id"] and s["summary"]["by_status"]["covered"] == 2
    text = client.get(f"/projects/{pid}/sources/{s['source_id']}").json()["masked_text"]
    assert "(follow-up: vague)" in text and "Topic coverage:" in text and "Refer to: business_analyst" in text
    assert "Inconsistencies not resolved" not in text  # it was resolved in turn 5
    assert client.post(f"/projects/{pid}/interview-sessions/{sid}/reply", json={"answer": "x"}).status_code == 409
    assert client.get(f"/projects/{pid + 1000}/interview-sessions/{sid}").status_code == 404
    audit = client.get(f"/projects/{pid}/audit").json()
    done = next(a for a in audit if a["action"] == "interview_completed")
    assert done["detail"]["follow_ups"] == 3 and done["detail"]["contradictions"] == 1
