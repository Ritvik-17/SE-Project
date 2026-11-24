"""SDLC selection engine: deterministic rules + multi-criteria decision analysis (TOPSIS + weighted fit).

Research and the provenance of every rule: guide/sdlc_selection_research_and_rules.md.

Criteria (all benefit criteria in [0, 1], higher = better fit for the model):
  - one per project factor: closeness of the project's 1-5 value to the model's ideal value
    (1 = exact match, 0 = opposite ends of the scale). Weights grow with the project's own factor value, so what
    matters most for this project counts most.
  - one per characteristic category of the course matrices (requirements, project team, user community, project type
    and risk): share of the project's yes/no answers that match the model's column. Categories with no answers are
    left out.
TOPSIS ranks models by relative closeness to the ideal solution; the weighted fit keeps scores interpretable.
Rules then add or subtract points, and every adjustment is reported with its source. The raw total is mapped to a
saturating 0-100 % suitability (`suitability()`), which keeps the order and keeps strong candidates distinguishable.
"""

import math
import operator
import re
from functools import lru_cache

import yaml

from app.catalog.loader import DATA_DIR

OPS = {">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt, "==": operator.eq}
SDLC_RULES_KEY = "sdlc-selection-rules"


@lru_cache
def _file_catalog() -> dict:
    return yaml.safe_load((DATA_DIR / "sdlc_models.yaml").read_text(encoding="utf-8"))


def load_sdlc_catalog_versioned() -> tuple[dict, str]:
    """(catalog, version): the in-force KB version of the rules, else the bundled file."""
    from app.kb.lookup import in_force
    doc = in_force(SDLC_RULES_KEY)
    if doc is not None:
        return yaml.safe_load(doc.content), f"kb:{doc.version}"
    return _file_catalog(), f"file:sdlc_models.yaml@{_file_catalog().get('version', '1')}"


def load_sdlc_catalog() -> dict:
    return load_sdlc_catalog_versioned()[0]


# ---------- Answers to the course characteristic questions ----------

def yn(value) -> str | None:
    """Normalise yes/no answers (YAML reads bare yes/no as booleans)."""
    if value is True or (isinstance(value, str) and value.strip().lower() in ("yes", "y", "true")):
        return "yes"
    if value is False or (isinstance(value, str) and value.strip().lower() in ("no", "n", "false")):
        return "no"
    return None


def _cond(value: float, expr: str) -> bool:
    m = re.fullmatch(r"\s*(>=|<=|==|>|<)\s*(\d+)\s*", str(expr))
    if not m:
        raise ValueError(f"Bad rule condition: {expr}")
    return OPS[m.group(1)](value, int(m.group(2)))


def characteristic_questions(cat: dict | None = None) -> list[dict]:
    cat = cat or load_sdlc_catalog()
    return [q | {"category": c["id"], "category_name": c["name"]}
            for c in cat.get("characteristics", []) for q in c["questions"]]


def derive_answers(factors: dict, signals: dict, cat: dict | None = None) -> dict[str, dict]:
    """Answers that follow from measured data: {question_id: {"answer", "source", "reason"}}."""
    out = {}
    for q in characteristic_questions(cat):
        d = q.get("derive")
        if not d:
            continue
        key = d.get("factor") or d.get("signal")
        value = (factors if "factor" in d else signals).get(key)
        if not isinstance(value, (int, float)):
            continue
        for answer in ("yes", "no"):
            expr = d.get(answer, d.get(answer == "yes"))  # YAML may have turned the key into True/False
            if expr is not None and _cond(value, expr):
                out[q["id"]] = {"answer": answer, "source": "derived", "reason": f"{key} = {value} ({expr})"}
                break
    return out


def merge_answers(llm: dict[str, dict], derived: dict[str, dict], human: dict[str, str | None]) -> dict[str, dict]:
    """Precedence: a human answer, then a derived answer, then the LLM's. Unknown answers are kept as unknown."""
    merged: dict[str, dict] = {}
    for qid in {*llm, *derived, *human}:
        if yn(human.get(qid)):
            merged[qid] = {"answer": yn(human[qid]), "source": "human", "reason": "answered at the SDLC gate"}
        elif qid in derived:
            merged[qid] = derived[qid]
        elif qid in llm and yn(llm[qid].get("answer")):
            merged[qid] = {"answer": yn(llm[qid]["answer"]), "source": "llm", "reason": llm[qid].get("reason", "")}
        else:
            merged[qid] = {"answer": None, "source": "unknown", "reason": (llm.get(qid) or {}).get("reason", "")}
    return merged


def characteristic_fit(model_id: str, answers: dict[str, dict], cat: dict) -> dict[str, dict]:
    """Per category: share of answered questions where the model's column equals the project's answer."""
    out = {}
    for c in cat.get("characteristics", []):
        answered = [(q, answers[q["id"]]["answer"]) for q in c["questions"] if answers.get(q["id"], {}).get("answer")]
        if not answered:
            continue
        matched = [q["id"] for q, a in answered if yn(q["fits"].get(model_id)) == a]
        out[c["id"]] = {"score": len(matched) / len(answered), "matched": len(matched), "answered": len(answered),
                        "mismatched": [q["id"] for q, a in answered if q["id"] not in matched]}
    return out


# ---------- MCDA ----------

def _complete(factors: dict, defs: list[dict]) -> dict[str, int]:
    """Factors missing from the input (e.g. an older rules version) default to the neutral midpoint."""
    return {f["id"]: int(factors.get(f["id"], 3)) for f in defs} | {k: v for k, v in factors.items() if isinstance(v, int)}


def topsis(matrix: list[list[float]], weights: list[float]) -> list[float]:
    """Relative closeness (0-1) of each alternative to the ideal solution. All criteria are benefits."""
    cols = range(len(weights))
    norms = [math.sqrt(sum(row[j] ** 2 for row in matrix)) or 1.0 for j in cols]
    v = [[weights[j] * row[j] / norms[j] for j in cols] for row in matrix]
    best = [max(r[j] for r in v) for j in cols]
    worst = [min(r[j] for r in v) for j in cols]
    out = []
    for r in v:
        d_best = math.sqrt(sum((r[j] - best[j]) ** 2 for j in cols))
        d_worst = math.sqrt(sum((r[j] - worst[j]) ** 2 for j in cols))
        out.append(0.5 if d_best + d_worst == 0 else d_worst / (d_best + d_worst))
    return out


def _matches(cond_key: str, expr, factors: dict, answers: dict) -> bool:
    if cond_key.startswith("q."):
        return (answers.get(cond_key[2:]) or {}).get("answer") == yn(expr)
    return _cond(factors[cond_key], expr)


def rule_applies(rule: dict, factors: dict, answers: dict) -> bool:
    all_ok = all(_matches(k, v, factors, answers) for k, v in (rule.get("when") or {}).items())
    any_ok = any(_matches(k, v, factors, answers) for k, v in rule["when_any"].items()) if rule.get("when_any") else True
    return all_ok and any_ok


def suitability(raw: float, saturation: float = 50) -> int:
    """Map the raw score (MCDA base 0-100 plus rule points, which can exceed 100) to a 0-100 % suitability.

    Monotonic, so the ranking never changes, but it saturates smoothly instead of clamping: two strong candidates
    that both pass 100 raw points stay distinguishable (e.g. raw 120 -> 91 %, raw 100 -> 86 %, raw 70 -> 75 %).
    """
    return round(100 * (1 - math.exp(-max(0.0, raw) / saturation)))


def rank_sdlc_models(factors: dict, answers: dict[str, dict] | None = None, cat: dict | None = None) -> list[dict]:
    """Ranked recommendations with every component of the score, best first."""
    cat = cat or load_sdlc_catalog()
    answers = answers or {}
    defs, models = cat["factors"], cat["models"]
    factors = _complete(factors, defs)
    scoring = cat.get("scoring", {"w_topsis": 0.5, "w_fit": 0.5, "characteristic_weight": 1.2})
    names = {f["id"]: f["name"] for f in defs}

    # Criteria: factors, then the characteristic categories that have at least one answer
    char_fits = {m["id"]: characteristic_fit(m["id"], answers, cat) for m in models}
    char_ids = [c["id"] for c in cat.get("characteristics", []) if any(c["id"] in f for f in char_fits.values())]
    raw = {f["id"]: f["base_weight"] * (0.5 + factors[f["id"]] / 5) for f in defs}
    raw |= {c: scoring["characteristic_weight"] for c in char_ids}
    total = sum(raw.values())
    w = {k: v / total for k, v in raw.items()}
    criteria = [f["id"] for f in defs] + char_ids

    def perf(m: dict) -> list[float]:
        row = [1 - abs(factors[f["id"]] - m["ideal_profile"].get(f["id"], 3)) / 4 for f in defs]
        return row + [char_fits[m["id"]].get(c, {}).get("score", 0.5) for c in char_ids]

    matrix = [perf(m) for m in models]
    closeness = topsis(matrix, [w[c] for c in criteria])
    fired = [r for r in cat["rules"] if rule_applies(r, factors, answers)]

    ranked = []
    for m, p, c in zip(models, matrix, closeness):
        fit = sum(w[k] * p[j] for j, k in enumerate(criteria))
        adjustments = [{"rule": r["id"], "points": r["effects"][m["id"]], "reason": r["reason"], "source": r.get("source", "")}
                       for r in fired if m["id"] in r["effects"]]
        base = 100 * (scoring["w_topsis"] * c + scoring["w_fit"] * fit)
        raw = base + sum(a["points"] for a in adjustments)
        score = suitability(raw, scoring.get("saturation", 50))
        n_f = len(defs)
        contrib = sorted(((w[k] * p[j], k) for j, k in enumerate(criteria[:n_f])), reverse=True)
        mismatches = [k for j, k in enumerate(criteria[:n_f]) if p[j] <= 0.5]
        cf = char_fits[m["id"]]
        ranked.append({
            "model": m["name"], "model_id": m["id"], "score": score,
            "raw": round(raw, 1), "topsis": round(100 * c), "fit": round(100 * fit),
            "characteristics_fit": round(100 * sum(x["matched"] for x in cf.values()) / sum(x["answered"] for x in cf.values()))
            if cf else None,
            "characteristics": {k: {"matched": v["matched"], "answered": v["answered"], "mismatched": v["mismatched"]}
                                for k, v in cf.items()},
            "rule_adjustments": adjustments,
            "key_drivers": [f"{'high' if factors[k] >= 3 else 'low'} {names[k].lower()}" for _, k in contrib[:2]],
            "concerns": [f"{names[k]} {factors[k]} vs ideal {m['ideal_profile'].get(k, 3)}" for k in mismatches],
            "source": m.get("source", ""),
        })
    return sorted(ranked, key=lambda r: (r["raw"], r["topsis"]), reverse=True)


def rules_fired(factors: dict, answers: dict[str, dict] | None = None, cat: dict | None = None) -> list[dict]:
    cat = cat or load_sdlc_catalog()
    factors = _complete(factors, cat["factors"])
    return [{"rule": r["id"], "reason": r["reason"], "source": r.get("source", ""), "effects": r["effects"]}
            for r in cat["rules"] if rule_applies(r, factors, answers or {})]
