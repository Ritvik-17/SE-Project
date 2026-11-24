"""Step 19 evaluation: metric definitions on known inputs, and the automated runner end to end (stubbed LLM)."""

import json

from app import llm
from app.security import rbac
from eval import metrics as M


def test_prf_and_greedy_matching():
    assert M.prf(8, 2, 4) == {"precision": 0.8, "recall": 0.667, "f1": 0.727, "tp": 8, "fp": 2, "fn": 4}
    sim = [[0.95, 0.90, 0.10], [0.92, 0.50, 0.20], [0.30, 0.40, 0.79]]
    m = M.match(sim, 0.80)
    assert m == {0: (0, 0.95)}  # one-to-one: gold 1's best partner is taken; 0.79 is below threshold
    assert M.match(sim, 0.75) == {0: (0, 0.95), 2: (2, 0.79)}


def test_sus_satisfaction_and_time():
    assert M.sus_score([5, 1, 5, 1, 5, 1, 5, 1, 5, 1]) == 100.0 and M.sus_score([3] * 10) == 50.0
    s = M.satisfaction([{"role": "customer", "sus": [4, 2] * 5, "usefulness": 4, "trust": 3}])
    assert s["sus_mean"] == 75.0 and s["responses"] == 1
    audit = [{"at": "2026-10-01T10:00:00+00:00", "principal": None, "action": "pass_started"},
             {"at": "2026-10-01T10:05:00+00:00", "principal": None, "action": "validated"},
             {"at": "2026-10-01T10:35:00+00:00", "principal": "ba", "action": "baseline_approve"},
             {"at": "2026-10-01T10:37:00+00:00", "principal": None, "action": "artifacts_generated"}]
    t = M.time_saved(audit, 10.0, {"ba"})
    assert t["ai_processing_minutes"] == 7.0 and t["human_review_minutes"] == 30.0
    assert t["time_saved_pct"] == round(100 * (1 - (37 / 60) / 10), 1)
    assert M.time_saved(audit, None, {"ba"})["time_saved_pct"] is None


def test_hallucination_traceability_and_sdlc():
    preds = [{"id": "FR-1", "source_id": 1, "source_quote": "apply on my phone", "citations": []},
             {"id": "FR-2", "source_id": 1, "source_quote": "approve all loans instantly", "citations": []}]
    h = M.hallucination(preds, {1: "I want to apply on my phone."}, {"FR-1": {"citations": [{"ref": "KB-1"}], "dropped_refs": ["KB-9"]}}, {})
    assert h["unsupported_quotes"] == ["FR-2"] and h["claims_checked"] == 4 and h["rate"] == 0.5
    rtm = [{"req_id": "FR-1", "stakeholder_role": "customer", "origin": "extracted", "tests": 2, "categories": ["functional"],
            "type": "functional", "use_cases": ["UC-01"], "user_story": True, "sdlc_phase": "Design", "regulations": [], "citations": []}]
    tr = M.traceability(rtm, preds, {1: "I want to apply on my phone."})
    assert tr["full_chain"] == 1.0
    ranking = [{"model_id": "agile_v_hybrid"}, {"model_id": "v_model"}, {"model_id": "waterfall"}]
    acc = M.sdlc_accuracy(ranking, ["v_model", "v_model", "agile_v_hybrid"])
    assert acc["expert_majority"] == "v_model" and not acc["top1_match"] and acc["top3_hit"] and acc["reciprocal_rank"] == 0.5


def test_sdlc_benchmark_runs_and_marks_label_source():
    from eval.sdlc_benchmark import run
    report = run()
    assert report["summary"]["scenarios"] == 11
    assert all(r["label_source"] in ("experts", "author_reference") for r in report["scenarios"])


def test_automated_run_end_to_end(monkeypatch, fake_embeddings):
    """The runner drives every gate through the real API and scores the result (LLM stubbed: values are not meaningful)."""
    from eval.run import automated
    from tests.test_flow import fake_structured
    monkeypatch.setattr(llm, "call_model", fake_structured)
    monkeypatch.setattr(rbac, "authenticate_request", rbac.authenticate_request)  # restored after the test
    report = automated("loan_digital_lending")
    assert report["project"]["id"] and report["mode"] == "automated:accept"
    m = report["metrics"]
    for key in ("extraction", "completeness", "ambiguity_detection", "conflict_detection", "regulatory_control_coverage",
                "hallucination", "citation_correctness", "sdlc_recommendation", "human_correction", "time",
                "stakeholder_satisfaction", "traceability"):
        assert key in m, key
    assert m["sdlc_recommendation"]["label_source"] == "author_reference"
    assert m["time"]["time_saved_pct"] is None  # no manual baseline recorded yet
    assert report["counts"]["gold_requirements"] == 43 and report["fingerprint"]
    assert set(report["checks"]) >= {"extraction_f1", "hallucination_rate"}
    md = open(report["files"][1], encoding="utf-8").read()
    assert "| Requirement extraction |" in md and "LLM usage" in md
    from app.db import SessionLocal
    from app.models import EvaluationRun, LlmCall
    with SessionLocal() as s:
        assert s.query(EvaluationRun).filter_by(project_id=report["project"]["id"]).count() == 1
        calls = s.query(LlmCall).filter_by(project_ref=report["project"]["id"]).all()
    assert calls and all(c.prompt and c.response for c in calls)  # every model call recorded (encrypted at rest)
    assert any(c.model == "gpt-4.1-nano" for c in calls) and any(c.model == "gpt-4.1-mini" for c in calls)  # routing
    json.dumps(report, default=str)
