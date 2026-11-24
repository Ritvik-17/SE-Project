"""SDLC recommendation accuracy against experienced architects and project managers (step 19).

  python -m eval.sdlc_benchmark            prints the report and writes eval/reports/sdlc-benchmark-<time>.json

Experts record their first, second and third choices per scenario in eval/sdlc/expert_labels.csv without seeing the
engine's output. Rows with expert_id "author_reference" are the project author's labels; they are used only for
scenarios with no real expert rows, and the report says which kind of label each result is based on.
Runs the deterministic engine only: no LLM, no cost.
"""

import csv
import json
from datetime import datetime
from pathlib import Path

import yaml

from app.rules.sdlc import _file_catalog, derive_answers, merge_answers, rank_sdlc_models
from eval.metrics import sdlc_accuracy

HERE = Path(__file__).parent
REPORTS = HERE / "reports"


def load_labels() -> dict[str, list[dict]]:
    rows: dict[str, list[dict]] = {}
    with open(HERE / "sdlc" / "expert_labels.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.setdefault(row["scenario_id"], []).append(row)
    return rows


def run() -> dict:
    cat = _file_catalog()
    scenarios = yaml.safe_load((HERE / "sdlc" / "scenarios.yaml").read_text(encoding="utf-8"))["scenarios"]
    labels = load_labels()
    neutral = {f["id"]: 3 for f in cat["factors"]}
    results = []
    for s in scenarios:
        factors = neutral | s["factors"]
        answers = merge_answers({}, derive_answers(factors, {}, cat), s.get("answers") or {})
        ranking = rank_sdlc_models(factors, answers, cat)
        rows = labels.get(s["id"], [])
        experts = [r for r in rows if r["expert_id"] != "author_reference"]
        used = experts or [r for r in rows if r["expert_id"] == "author_reference"]
        acc = sdlc_accuracy(ranking, [r["choice_1"] for r in used])
        pairwise = [a["choice_1"] == b["choice_1"] for i, a in enumerate(experts) for b in experts[i + 1:]]
        results.append({"scenario": s["id"], "label_source": "experts" if experts else ("author_reference" if used else "none"),
                        "engine_ranking": [(r["model_id"], r["score"]) for r in ranking[:3]], **acc,
                        "expert_agreement": round(sum(pairwise) / len(pairwise), 3) if pairwise else None})
    scored = [r for r in results if "top1_match" in r]
    summary = {
        "scenarios": len(results), "scored": len(scored),
        "top1_accuracy": round(sum(r["top1_match"] for r in scored) / len(scored), 3) if scored else None,
        "top3_hit_rate": round(sum(r["top3_hit"] for r in scored) / len(scored), 3) if scored else None,
        "mean_reciprocal_rank": round(sum(r["reciprocal_rank"] for r in scored) / len(scored), 3) if scored else None,
        "scored_against_real_experts": sum(r["label_source"] == "experts" for r in scored),
        "rules_version": cat.get("version"),
    }
    return {"summary": summary, "scenarios": results}


if __name__ == "__main__":
    report = run()
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / f"sdlc-benchmark-{datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    s = report["summary"]
    print(f"SDLC benchmark: top-1 {s['top1_accuracy']} · top-3 {s['top3_hit_rate']} · MRR {s['mean_reciprocal_rank']} "
          f"({s['scored_against_real_experts']}/{s['scored']} scenarios scored against real experts)")
    for r in report["scenarios"]:
        print(f"  {r['scenario']:30s} engine={r.get('engine_top1')!s:24s} expert={r.get('expert_majority')!s:24s} "
              f"{'OK' if r.get('top1_match') else 'top3' if r.get('top3_hit') else 'MISS'} [{r['label_source']}]")
    print(f"Wrote {out}")
