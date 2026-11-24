"""Run and score an evaluation case (problem statement step 19).

  Automated run (needs OPENAI_API_KEY; costs real tokens; creates a project "EVAL ..." you can open in the UI):
    python -m eval.run --case loan_digital_lending

  Score a project you ran yourself through the UI (human-review mode: real corrections and review time):
    python -m eval.run --case loan_digital_lending --project 42

Options: --threshold 0.80 (gold/predicted matching), --reviewer accept|gold (automated mode: accept everything, or
reject requirements that match no gold requirement, simulating a business analyst).

Writes eval/reports/<case>-<mode>-<time>.json and .md, and stores the result in `evaluation_runs` with the
provenance fingerprint (model, prompts, rules, knowledge-base versions) it was produced under.
"""

import argparse
import copy
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path

import yaml
from sqlalchemy import select

from eval import metrics as M

HERE = Path(__file__).parent
EVAL_USER = "eval_runner"


# ---------- Provenance ----------

def fingerprint(prov: dict) -> str:
    from app.security.provenance import fingerprint as fp
    return fp(prov)


# ---------- Loading ----------

def load_case(case_id: str) -> tuple[dict, dict, Path]:
    folder = HERE / "cases" / case_id
    case = yaml.safe_load((folder / "case.yaml").read_text(encoding="utf-8"))
    gold = yaml.safe_load((folder / "gold.yaml").read_text(encoding="utf-8"))
    return case, gold, folder


def gather(graph, project_id: int) -> dict:
    """Everything the metrics need, read in-process (full state, including source text)."""
    from app.db import SessionLocal
    from app.models import Artifact, AuditLog, Feedback, LlmCall, Project

    state = graph.get_state({"configurable": {"thread_id": f"project-{project_id}-v2"}}).values or {}
    with SessionLocal() as s:
        audit = [{"at": a.created_at.isoformat(), "actor": a.actor, "principal": a.principal, "action": a.action,
                  "detail": a.detail} for a in s.scalars(select(AuditLog).where(AuditLog.project_ref == project_id))]
        calls = s.scalars(select(LlmCall).where(LlmCall.project_ref == project_id)).all()
        usage = {"calls": len(calls), "input_tokens": sum(c.input_tokens for c in calls),
                 "cached_tokens": sum(c.cached_tokens for c in calls), "output_tokens": sum(c.output_tokens for c in calls),
                 "cost_usd": round(sum(c.cost_usd for c in calls), 4),
                 "by_agent": {}, "by_model": {}}
        for c in calls:
            for key, name in (("by_agent", c.agent), ("by_model", c.model)):
                row = usage[key].setdefault(name, {"calls": 0, "tokens": 0, "cost_usd": 0.0})
                row["calls"] += 1
                row["tokens"] += c.input_tokens + c.output_tokens
                row["cost_usd"] = round(row["cost_usd"] + c.cost_usd, 4)
        artifacts = {a.kind: a.content["data"] for a in s.scalars(select(Artifact).where(Artifact.project_id == project_id,
                                                                                         Artifact.superseded_at.is_(None)))}
        feedback = [{"role": f.role, "sus": f.sus, "usefulness": f.usefulness, "trust": f.trust}
                    for f in s.scalars(select(Feedback).where(Feedback.project_id == project_id))]
        project = s.get(Project, project_id)
    return {"state": state, "audit": audit, "usage": usage, "artifacts": artifacts, "feedback": feedback,
            "project": {"id": project_id, "name": project.name if project else None, "domain": project.domain if project else None}}


def ai_requirements(state: dict) -> list[dict]:
    """The AI's own output: extracted requirements with their original wording, including ones humans rejected."""
    out = []
    for r in state.get("requirements", []):
        if r.get("origin", "extracted") != "extracted":
            continue
        out.append(r | {"statement": r.get("original_statement", r["statement"])})
    return out


# ---------- Scoring ----------

def score(case: dict, gold: dict, data: dict, *, mode: str, threshold: float = 0.80, snapshot: list[dict] | None = None,
          sdlc_ranking: list[dict] | None = None, human_actors: set[str] | None = None) -> dict:
    from app.catalog.loader import get_catalog
    from eval.sdlc_benchmark import load_labels

    state, arts = data["state"], data["artifacts"]
    predicted = snapshot if snapshot is not None else ai_requirements(state)
    gold_reqs = gold["requirements"]
    sim = M.similarity_matrix([g["statement"] for g in gold_reqs], [p["statement"] for p in predicted])
    m = M.match(sim, threshold)
    baseline = [r for r in state.get("requirements", []) if r.get("status") not in ("rejected", "suggested")]
    source_text = {s["id"]: s.get("text", "") for s in state.get("sources", [])}
    domain = get_catalog().domain(case["domain"])

    texts = [r["statement"] for r in baseline] + [f"{x['regulation']}: {x['obligation']}"
                                                  for x in state.get("compliance", {}).get("mappings", [])]
    labels = [r["choice_1"] for r in load_labels().get(gold.get("sdlc_scenario", ""), []) if r["expert_id"] != "author_reference"]
    ref_labels = [r["choice_1"] for r in load_labels().get(gold.get("sdlc_scenario", ""), []) if r["expert_id"] == "author_reference"]
    ranking = sdlc_ranking or state.get("sdlc_recommendations", [])
    sdlc = M.sdlc_accuracy(ranking, labels or ref_labels) if ranking else {"status": "not reached"}
    if ranking:
        sdlc["label_source"] = "experts" if labels else "author_reference"
        sdlc["approved_model"] = state.get("sdlc_decision", {}).get("model")

    report = {
        "case": case["id"], "mode": mode, "project": data["project"], "generated_at": datetime.now().isoformat(timespec="seconds"),
        "gold_version": gold.get("version"), "matching_threshold": threshold,
        "counts": {"gold_requirements": len(gold_reqs), "ai_requirements": len(predicted), "baseline_requirements": len(baseline)},
        "metrics": {
            "extraction": M.extraction_scores(gold_reqs, predicted, sim, threshold),
            "extraction_sensitivity": {str(t): M.extraction_scores(gold_reqs, predicted, sim, t)["f1"] for t in (0.75, 0.80, 0.85)},
            "completeness": M.completeness(gold_reqs, m, baseline, domain.mandatory_categories if domain else []),
            "ambiguity_detection": M.ambiguity_detection(gold_reqs, predicted, m, state.get("issues", []), state.get("clarifications", [])),
            "conflict_detection": M.conflict_detection(gold_reqs, gold.get("conflicts", []), predicted, m, state.get("conflicts", [])),
            "policy_contradictions": M.policy_contradictions(gold_reqs, predicted, m, gold.get("policy_contradictions", [])),
            "regulatory_control_coverage": M.control_coverage(gold.get("controls", []), texts),
            "hallucination": M.hallucination(predicted, source_text, state.get("grounding", {}), state.get("compliance", {})),
            "citation_correctness": M.citation_correctness(gold_reqs, predicted, m, state.get("compliance", {})),
            "sdlc_recommendation": sdlc,
            "human_correction": M.human_correction(state.get("requirements", []), state.get("compliance", {}),
                                                   state.get("sdlc_approvals", []), state.get("sdlc_workflow", {})),
            "time": M.time_saved(data["audit"], (case.get("manual_baseline") or {}).get("analyst_hours"), human_actors or set()),
            "stakeholder_satisfaction": M.satisfaction(data["feedback"]),
            "traceability": M.traceability(arts.get("traceability_matrix", []), state.get("requirements", []), source_text),
        },
        "usage": data["usage"],
        "matches": [{"gold": gold_reqs[gi]["id"], "requirement": predicted[pi]["id"], "similarity": s,
                     "gold_statement": gold_reqs[gi]["statement"], "ai_statement": predicted[pi]["statement"]}
                    for gi, (pi, s) in sorted(m.items())],
        "unmatched_gold": [g["id"] for i, g in enumerate(gold_reqs) if i not in m],
        "unmatched_ai": [p["id"] for i, p in enumerate(predicted) if i not in {pi for pi, _ in m.values()}],
        "provenance": state.get("provenance", {}),
    }
    report["checks"], report["passed"] = check_thresholds(report["metrics"])
    return report


def check_thresholds(metrics: dict) -> tuple[dict, bool]:
    t = yaml.safe_load((HERE / "thresholds.yaml").read_text(encoding="utf-8"))
    values = {
        "extraction_f1": metrics["extraction"]["f1"], "must_have_recall": metrics["completeness"]["must_have_recall"],
        "ambiguity_recall": metrics["ambiguity_detection"]["recall"], "conflict_recall": metrics["conflict_detection"]["recall"],
        "control_coverage": metrics["regulatory_control_coverage"]["coverage"], "hallucination_rate": metrics["hallucination"]["rate"],
        "citation_correctness": metrics["citation_correctness"]["correctness"],
        "traceability_full_chain": metrics["traceability"]["full_chain"],
    }
    checks = {}
    for k, rule in t.items():
        v = values.get(k)
        ok = v is None or (("min" not in rule or v >= rule["min"]) and ("max" not in rule or v <= rule["max"]))
        checks[k] = {"value": v, **rule, "ok": ok}
    return checks, all(c["ok"] for c in checks.values())


# ---------- Automated run ----------

def _principal():
    from app.catalog.loader import get_catalog
    from app.db import SessionLocal
    from app.models import User
    from app.security import auth, rbac

    roles = [r.id for r in get_catalog().roles]
    with SessionLocal.begin() as s:
        user = s.scalar(select(User).where(User.username == EVAL_USER))
        if user is None:  # an inactive service account: it cannot sign in through the web, only run here in-process
            import secrets
            user = auth.create_user(s, EVAL_USER, "Evaluation runner", "Ev-" + secrets.token_urlsafe(16) + "9a", roles)
        user.active, user.roles = False, roles
        uid = user.id
    return rbac.Principal(uid, EVAL_USER, "Evaluation runner", roles, True)


def automated(case_id: str, reviewer: str = "accept", threshold: float = 0.80) -> dict:
    from fastapi.testclient import TestClient

    from app.api.main import app
    from app.security import rbac

    case, gold, folder = load_case(case_id)
    principal = _principal()
    rbac.authenticate_request = lambda _request: principal  # in-process only: this command already has DB access
    started = time.perf_counter()
    with TestClient(app) as c:
        def ok(r):
            if r.status_code >= 400:
                raise RuntimeError(f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text[:300]}")
            return r.json()
        pid = ok(c.post("/projects", json={"name": f"EVAL {case['name'][:120]} {datetime.now():%m-%d %H:%M}",
                                            "domain": case["domain"], "jurisdiction": case["jurisdiction"]}))["id"]
        for s in case["sources"]:
            path = folder / "inputs" / s["file"]
            form = {"source_type": s["source_type"], "stakeholder_role": s["stakeholder_role"], "title": s["title"]}
            ok(c.post(f"/projects/{pid}/sources", data=form, files={"file": (path.name, path.read_bytes())}))
        print(f"Project {pid}: {len(case['sources'])} sources added; running the agents…")
        run = ok(c.post(f"/projects/{pid}/runs"))
        snapshot, sdlc_answered, sdlc_ranking, gold_ids = None, False, None, None
        for _ in range(30):
            if run["status"] != "awaiting_input":
                break
            gate, p = run["gate"], run["pending"]
            print(f"  gate: {gate}")
            if gate == "clarification":
                answers = []
                for q in p["questions"]:
                    text = q["question"].lower()
                    hit = next((a["answer"] for a in case["clarification_answers"] if any(k in text for k in a["keywords"])), "")
                    answers.append({"question": q["question"], "target_role": q["target_role"], "answer": hit})
                run = ok(c.post(f"/projects/{pid}/decision", json={"gate": "clarification", "answers": answers,
                                                                   "skip": not any(a["answer"] for a in answers)}))
            elif gate == "baseline":
                if snapshot is None:
                    snapshot = copy.deepcopy([r for r in p["requirements"] if r.get("origin", "extracted") == "extracted"])
                    if reviewer == "gold":
                        sim = M.similarity_matrix([g["statement"] for g in gold["requirements"]], [r["statement"] for r in snapshot])
                        gold_ids = {snapshot[pi]["id"] for pi, _ in M.match(sim, threshold).values()}
                role = p["pending_approvers"][0]
                edits = [{"id": i, "action": "reject" if reviewer == "gold" and gold_ids is not None and i not in gold_ids
                          and i in {r["id"] for r in snapshot} else "accept"}
                         for i, it in p.get("decision_items", {}).items() if it["owner"] == role and not it["decided"]]
                legal = [{"id": m["id"], "action": "accept"} for m in p.get("interpretations", [])
                         if not m.get("legal_decision")] if role == "compliance_legal" else []
                run = ok(c.post(f"/projects/{pid}/decision", json={"gate": "baseline", "decision": "approve", "reviewer": EVAL_USER,
                                                                   "reviewer_role": role, "edits": edits, "interpretations": legal}))
            elif gate == "sdlc":
                if not sdlc_answered:
                    sdlc_answered = True
                    run = ok(c.post(f"/projects/{pid}/decision", json={
                        "gate": "sdlc", "decision": "regenerate", "reviewer": EVAL_USER, "reviewer_role": "project_manager",
                        "characteristic_answers": case.get("sdlc_characteristics", {})}))
                    continue
                sdlc_ranking = sdlc_ranking or p["recommendations"]
                run = ok(c.post(f"/projects/{pid}/decision", json={"gate": "sdlc", "decision": "approve", "reviewer": EVAL_USER,
                                                                   "reviewer_role": p["pending_approvers"][0]}))
            elif gate == "workflow":
                run = ok(c.post(f"/projects/{pid}/decision", json={"gate": "workflow", "decision": "approve", "reviewer": EVAL_USER,
                                                                   "reviewer_role": p["pending_approvers"][0]}))
        if run["status"] != "completed":
            raise RuntimeError(f"Run did not complete (status {run['status']}, gate {run.get('gate')})")
        data = gather(app.state.graph, pid)
    report = score(case, gold, data, mode=f"automated:{reviewer}", threshold=threshold, snapshot=snapshot,
                   sdlc_ranking=sdlc_ranking, human_actors=set())
    report["wall_clock_minutes"] = round((time.perf_counter() - started) / 60, 1)
    return save(report)


def score_project(case_id: str, project_id: int, threshold: float = 0.80) -> dict:
    from fastapi.testclient import TestClient

    from app.api.main import app
    from app.db import SessionLocal
    from app.models import User

    case, gold, _ = load_case(case_id)
    with TestClient(app):  # starts the app so the graph and checkpointer exist
        data = gather(app.state.graph, project_id)
    with SessionLocal() as s:
        humans = {u.username for u in s.scalars(select(User)) if u.username != EVAL_USER}
    return save(score(case, gold, data, mode="human_review", threshold=threshold, human_actors=humans))


# ---------- Output ----------

def save(report: dict) -> dict:
    from app.db import SessionLocal
    from app.models import EvaluationRun

    prov = report.get("provenance") or {}
    report["fingerprint"] = fingerprint(prov)
    with SessionLocal.begin() as s:
        s.add(EvaluationRun(case_id=report["case"], domain=report["project"].get("domain"), mode=report["mode"],
                            project_id=report["project"]["id"],
                            fingerprint=report["fingerprint"], provenance=prov, metrics=report["metrics"] | {"usage": report["usage"]},
                            passed=report["passed"], created_by="eval_cli"))
    out = HERE / "reports"
    out.mkdir(exist_ok=True)
    stem = f"{report['case']}-{report['mode'].replace(':', '-')}-{datetime.now():%Y%m%d-%H%M%S}"
    (out / f"{stem}.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (out / f"{stem}.md").write_text(markdown(report), encoding="utf-8")
    report["files"] = [str(out / f"{stem}.json"), str(out / f"{stem}.md")]
    return report


def markdown(r: dict) -> str:
    m = r["metrics"]
    pct = lambda v: "n/a" if v is None else f"{100 * v:.0f}%"  # noqa: E731
    t = m["time"]
    sdlc = m["sdlc_recommendation"]
    rows = [
        ("Requirement extraction", f"P {pct(m['extraction']['precision'])} · R {pct(m['extraction']['recall'])} · F1 {pct(m['extraction']['f1'])}",
         f"{m['extraction']['tp']} matched, {m['extraction']['fp']} extra, {m['extraction']['fn']} missed (threshold {r['matching_threshold']}; F1 at 0.75/0.80/0.85: {', '.join(pct(v) for v in m['extraction_sensitivity'].values())})"),
        ("Requirement completeness", pct(m["completeness"]["score"]),
         f"must-have recall {pct(m['completeness']['must_have_recall'])}, mandatory categories {pct(m['completeness']['mandatory_category_coverage'])}, record fields {pct(m['completeness']['record_field_completeness'])}"),
        ("Ambiguity detection", f"accuracy {pct(m['ambiguity_detection']['accuracy'])} · recall {pct(m['ambiguity_detection']['recall'])}",
         f"precision {pct(m['ambiguity_detection']['precision'])} over {m['ambiguity_detection']['evaluated']} matched requirements"),
        ("Conflict detection", f"P {pct(m['conflict_detection']['precision'])} · R {pct(m['conflict_detection']['recall'])}",
         f"detected {m['conflict_detection']['detected']}, missed {m['conflict_detection']['missed']}; policy contradictions found {m['policy_contradictions']['detected']}"),
        ("Regulatory-control coverage", pct(m["regulatory_control_coverage"]["coverage"]), f"missing {m['regulatory_control_coverage']['missing']}"),
        ("Hallucination rate", pct(m["hallucination"]["rate"]),
         f"unsupported quotes {pct(m['hallucination']['unsupported_quote_rate'])}, invented citations removed {m['hallucination']['invented_citations_removed']}"),
        ("Citation correctness", pct(m["citation_correctness"]["correctness"]),
         f"{m['citation_correctness']['correct']}/{m['citation_correctness']['checked']} citations from the expected document ({m['citation_correctness']['unverifiable']} not checkable)"),
        ("SDLC recommendation", "match" if sdlc.get("top1_match") else ("top-3" if sdlc.get("top3_hit") else sdlc.get("status", "miss")),
         f"engine {sdlc.get('engine_top1')} vs {sdlc.get('label_source', '')} {sdlc.get('expert_majority')}"),
        ("Human correction rate", pct(m["human_correction"]["rate"]),
         f"{m['human_correction']['requirements_corrected']}/{m['human_correction']['requirements_total']} requirements, {m['human_correction']['interpretations_corrected']} interpretations, SDLC override {m['human_correction']['sdlc_override']}"),
        ("Time saved", "not measured" if t["time_saved_pct"] is None else f"{t['time_saved_pct']}%",
         f"AI {t['ai_processing_minutes']} min + human review {t['human_review_minutes']} min vs manual {t['manual_hours'] or 'not recorded'} h"),
        ("Stakeholder satisfaction", "no responses" if not m["stakeholder_satisfaction"].get("responses") else f"SUS {m['stakeholder_satisfaction']['sus_mean']}",
         f"{m['stakeholder_satisfaction'].get('responses', 0)} responses"),
        ("Traceability coverage", pct(m["traceability"]["full_chain"]), ", ".join(f"{k} {pct(v)}" for k, v in m["traceability"]["by_link"].items())),
    ]
    u = r["usage"]
    lines = [f"# Evaluation: {r['case']} ({r['mode']})", "",
             f"Project {r['project']['id']} · {r['generated_at']} · gold v{r['gold_version']} · fingerprint `{r['fingerprint'][:12]}` · "
             f"**{'PASSED' if r['passed'] else 'NOT PASSED'}** against eval/thresholds.yaml", "",
             "| Metric | Result | Detail |", "|---|---|---|"] + [f"| {a} | {b} | {c} |" for a, b, c in rows] + [
             "", f"**LLM usage:** {u['calls']} calls · {u['input_tokens']:,} input ({u['cached_tokens']:,} cached) + {u['output_tokens']:,} output tokens · **${u['cost_usd']}**", "",
             "| Agent | Calls | Tokens | Cost (USD) |", "|---|---|---|---|"] + [
             f"| {a} | {v['calls']} | {v['tokens']:,} | {v['cost_usd']} |" for a, v in sorted(u["by_agent"].items(), key=lambda x: -x[1]["cost_usd"])] + [
             "", "## Threshold checks", "", "| Check | Value | Rule | OK |", "|---|---|---|---|"] + [
             f"| {k} | {v['value']} | {'≥ ' + str(v['min']) if 'min' in v else '≤ ' + str(v['max'])} | {'yes' if v['ok'] else 'NO'} |" for k, v in r["checks"].items()] + [
             "", "## Gold requirements not found", "", ", ".join(r["unmatched_gold"]) or "none",
             "", "## AI requirements with no gold match (review: extra detail, or noise?)", "", ", ".join(r["unmatched_ai"]) or "none"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", required=True)
    ap.add_argument("--project", type=int, help="score an existing project (human-review mode)")
    ap.add_argument("--reviewer", choices=["accept", "gold"], default="accept")
    ap.add_argument("--threshold", type=float, default=0.80)
    args = ap.parse_args()
    result = score_project(args.case, args.project, args.threshold) if args.project else \
        automated(args.case, args.reviewer, args.threshold)
    print(markdown(result))
    print("Files:", *result["files"], sep="\n  ")
