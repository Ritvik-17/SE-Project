"""Retrieval-grounded generation (step 6): classify → retrieve → evidence → generate → cite + score → escalate."""

import json
import re

import pytest
from fastapi.testclient import TestClient

from app import llm
from app.api.main import app
from app.kb.grounding import answer_confidence, requirement_confidence, requirement_escalation
from app.schemas import GroundedAnswer, QueryClassification


def fake_structured(schema, prompt):
    if schema is QueryClassification:
        if "weather" in prompt:
            return QueryClassification(intent="out_of_scope", collections=[], search_queries=[], reason="unrelated")
        return QueryClassification(intent="internal_policy", collections=["policy_control"],
                                   search_queries=["loan record retention period"], reason="retention policy")
    if schema is GroundedAnswer:
        refs = re.findall(r"\[(KB-\d+)\]", prompt)
        if "hallucinate" in prompt:
            return GroundedAnswer(answer="Eight years, and also ten years for appeals.", insufficient_evidence=False,
                                  confidence=0.9, claims=[{"text": "Eight years", "refs": refs[:1]},
                                                          {"text": "Ten years for appeals", "refs": ["KB-999999"]}])
        return GroundedAnswer(answer="Loan files are kept for eight years after closure.", insufficient_evidence=False,
                              confidence=0.95, claims=[{"text": "Loan files are kept for eight years after closure",
                                                        "refs": refs[:1]}])
    raise AssertionError(schema)


@pytest.fixture
def client(fake_embeddings, monkeypatch):
    monkeypatch.setattr(llm, "call_model", fake_structured)
    with TestClient(app) as c:
        meta = {"doc_key": "test-retention-policy", "collection": "policy_control", "title": "Test retention policy",
                "issuer": "Test Bank", "license": "sample", "jurisdictions": ["IN"], "effective_from": "2025-01-01",
                "version": "1", "applicability": {"domains": ["loan_processing"]}}
        res = c.post("/kb/documents", data={"metadata": json.dumps(meta), "submitted_by": "t", "content":
                     "2. Retention schedule\nLoan files shall be retained for eight years after loan closure. "
                     "Loan record retention period is eight years."})
        if res.status_code == 200:  # first test in the session creates and approves it
            c.post(f"/kb/documents/{res.json()['document']['id']}/approve", json={"actor": "cco", "role": "compliance_legal"})
        yield c


def test_confidence_and_escalation_rules():
    assert requirement_confidence(0.9, "no_obligation_expected", 0.2, "none") == 0.9
    assert requirement_confidence(0.9, "supported", 1.0, "strong") == 0.95
    assert requirement_confidence(0.9, "contradicts_evidence", 1.0, "strong") == 0.5
    assert "contradicts an approved policy or regulation" in requirement_escalation(["functional"], "contradicts_evidence", 0.9)
    assert requirement_escalation(["security"], "unsupported", 0.7) == ["no approved source supports this obligation"]
    assert requirement_escalation(["usability"], "no_obligation_expected", 0.9) == []
    assert answer_confidence(0.9, 1.0, "strong", False) == 0.9
    assert answer_confidence(0.9, 0.5, "weak", False) == 0.27
    assert answer_confidence(0.9, 1.0, "strong", True) == 0.0


def test_grounded_answer_with_citations(client):
    res = client.post("/kb/ask", json={"question": "How long must we keep loan files? Ask raj@bank.in",
                                       "asked_by": "ba", "domain": "loan_processing"}).json()
    assert res["classification"]["intent"] == "internal_policy"                  # 1. classified
    assert res["evidence"] and res["evidence"][0]["title"] == "Test retention policy"  # 2. retrieved
    assert res["citations"][0]["citation"] == "Test retention policy v1 §2"      # 5. cited with clause
    assert res["claims"][0]["refs"] and res["components"]["citation_coverage"] == 1.0
    assert "raj@bank.in" not in res["question"]                                   # question masked before the LLM
    expected = round(0.95 * {"strong": 1.0, "weak": 0.6, "none": 0.25}[res["components"]["evidence_strength"]], 2)
    assert res["confidence"] == expected
    assert res["escalated"] == (expected < 0.6)


def test_unsupported_and_hallucinated_answers_escalate(client):
    bad = client.post("/kb/ask", json={"question": "Retention? hallucinate an extra rule", "asked_by": "ba"}).json()
    assert bad["escalated"] and bad["review_id"]
    assert bad["claims"][1]["invalid_refs"] == ["KB-999999"] and bad["components"]["citation_coverage"] == 0.5
    assert any("without a valid citation" in r for r in bad["escalation_reasons"])
    assert any("possible hallucination" in r for r in bad["escalation_reasons"])

    off = client.post("/kb/ask", json={"question": "What is the weather in Mumbai?", "asked_by": "ba"}).json()
    assert off["escalated"] and off["confidence"] == 0.0 and off["evidence"] == []
    assert "insufficient evidence in approved sources" in off["escalation_reasons"]

    queue = client.get("/kb/review-queue").json()
    ids = {q["id"] for q in queue}
    assert {bad["review_id"], off["review_id"]} <= ids
    assert client.post(f"/kb/review-queue/{bad['review_id']}/resolve",
                       json={"actor": "cco", "role": "compliance_legal", "outcome": "corrected"}).status_code == 422
    assert client.post(f"/kb/review-queue/{bad['review_id']}/resolve",
                       json={"actor": "cco", "role": "compliance_legal", "outcome": "corrected",
                             "resolution": "Eight years only; there is no appeals rule."}).status_code == 200
    assert bad["review_id"] not in {q["id"] for q in client.get("/kb/review-queue").json()}
