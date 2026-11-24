"""Deterministic parts of the project-specific SDLC workflow (step 15).

The LLM fills each canonical phase of the chosen model with project-specific content and proposes durations; this
module turns that into a timeline that follows the model's structure, adds traceability requirements, normalises
approver roles and draws a Gantt chart. It never removes anything a human or the LLM wrote.

Recurrence of a canonical phase (sdlc_models.yaml):
  once           runs one time, in order
  per_iteration  runs inside every iteration / sprint / time-box (the iteration is split by phase durations)
  per_release    runs after every `iterations_per_release` iterations (release hardening)
  per_cycle      runs in every spiral cycle
  continuous     runs throughout the delivery window (pipeline stages, operation)
"""

from datetime import date, timedelta

from app.catalog.loader import get_catalog

LIMITS = {"iterations": (1, 20), "iteration_length_weeks": (1, 6), "iterations_per_release": (0, 12), "cycles": (1, 6)}
DURATION = (0.2, 26.0)

# Traceability every phase of a kind must maintain (added when the generated plan leaves it out).
TRACEABILITY_BY_KIND = {
    "requirements": "Every requirement keeps its ID, source stakeholder statement and acceptance criteria in the RTM",
    "design": "Design elements and threat-model entries reference the requirement IDs they realise",
    "implementation": "Commits and pull requests reference the story or requirement ID they implement",
    "testing": "Every test case references a requirement ID; RTM test status is updated from test results",
    "validation": "Acceptance results are recorded against requirement IDs and signed off in the RTM",
    "release": "Release notes list the requirement IDs delivered; the RTM records the release for each",
    "operation": "Incidents and changes are linked to requirement IDs through approved change requests",
    "risk": "Each risk decision is linked to the requirement IDs and risk-register entries it affects",
    "plan": "The plan for the period lists the requirement IDs selected for it",
    "review": "Review outcomes that change requirements are raised as change requests against requirement IDs",
    "prototype": "Each prototype loop records the user feedback and the requirement IDs it confirmed or changed",
}


def clamp(value, key: str, default):
    lo, hi = LIMITS[key]
    try:
        v = type(lo)(round(float(value))) if key != "iteration_length_weeks" else float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def schedule_params(proposed: dict, execution: dict) -> dict:
    """Iteration / cycle settings: the LLM's (or a human's) proposal within bounds, else the model's defaults."""
    out = {}
    for key in ("iterations", "iteration_length_weeks", "iterations_per_release", "cycles"):
        default = execution.get(key)
        if default is None:
            continue
        out[key] = clamp(proposed.get(key) if proposed.get(key) is not None else default, key, default)
    return out


def _dur(phase: dict) -> float:
    try:
        d = float(phase.get("duration_weeks") or 1.0)
    except (TypeError, ValueError):
        d = 1.0
    return round(max(DURATION[0], min(DURATION[1], d)), 1)


def build_schedule(phases: list[dict], structure: str, params: dict) -> dict:
    """Occurrences (start/end week, 0-based) of every phase, following the model's structure."""
    occ: dict[str, list[dict]] = {p["name"]: [] for p in phases}
    t = 0.0

    def run(p: dict, start: float, length: float, label: str) -> float:
        occ[p["name"]].append({"start": round(start, 1), "end": round(start + length, 1), "label": label})
        return start + length

    loop_kinds = ("per_iteration", "per_cycle")
    first_loop = next((i for i, p in enumerate(phases) if p["recurrence"] in loop_kinds), None)
    setup = [p for i, p in enumerate(phases) if p["recurrence"] == "once" and (first_loop is None or i < first_loop)]
    tail = [p for i, p in enumerate(phases) if p["recurrence"] == "once" and first_loop is not None and i > first_loop]
    loop = [p for p in phases if p["recurrence"] in loop_kinds]
    releases = [p for p in phases if p["recurrence"] == "per_release"]
    continuous = [p for p in phases if p["recurrence"] == "continuous"]

    for p in setup:
        t = run(p, t, _dur(p), p["name"])
    delivery_start = t

    if loop and structure == "cyclic":
        for c in range(1, params.get("cycles", 3) + 1):
            for p in loop:
                t = run(p, t, _dur(p), f"Cycle {c}")
    elif loop:
        n, length = params.get("iterations", 6), params.get("iteration_length_weeks", 2)
        per_release = params.get("iterations_per_release", 0)
        share = sum(_dur(p) for p in loop)
        for i in range(1, n + 1):
            start = t
            for p in loop:  # phases inside one iteration, in proportion to their durations
                start = run(p, start, length * _dur(p) / share, f"Iteration {i}")
            t += length
            if releases and per_release and (i % per_release == 0 or i == n):
                for p in releases:
                    t = run(p, t, _dur(p), f"Release {len(occ[p['name']]) + 1}")
        if releases and not per_release:
            for p in releases:
                t = run(p, t, _dur(p), "Release")
    elif releases:
        for p in releases:
            t = run(p, t, _dur(p), "Release")

    for p in tail:
        t = run(p, t, _dur(p), p["name"])
    if continuous:
        if loop:  # pipeline stages / continuous verification span the delivery window
            end = t
            first_release = min((o["start"] for r in releases for o in occ[r["name"]]), default=delivery_start)
            for p in continuous:  # operation starts with the first release, everything else with delivery
                begin = first_release if "operation" in p.get("kinds", []) else delivery_start
                run(p, begin, max(end - begin, _dur(p)), "Continuous")
        else:  # e.g. Waterfall maintenance: starts after everything else
            for p in continuous:
                t = run(p, t, _dur(p), p["name"])
    total = max((o["end"] for os in occ.values() for o in os), default=0.0)
    return {"occurrences": occ, "total_weeks": round(total, 1)}


def _weeks(a: float, b: float) -> str:
    first, last = int(a) + 1, max(int(a) + 1, int(-(-b // 1)))
    return f"week {first}" if first == last else f"weeks {first}–{last}"


def timing_label(phase: dict, occurrences: list[dict], params: dict) -> str:
    if not occurrences:
        return "not scheduled"
    span = _weeks(occurrences[0]["start"], occurrences[-1]["end"])
    rec = phase["recurrence"]
    if rec == "per_iteration":
        return f"Every iteration ({len(occurrences)} × {params.get('iteration_length_weeks'):g} weeks), {span}"
    if rec == "per_cycle":
        return f"Every cycle ({len(occurrences)} cycles), {span}"
    if rec == "per_release":
        return f"At each release ({len(occurrences)}×): " + ", ".join(_weeks(o["start"], o["end"]) for o in occurrences)
    if rec == "continuous":
        return f"Continuous, {span}"
    return span[0].upper() + span[1:]


def gantt(model: str, phases: list[dict], occurrences: dict[str, list[dict]], start: date) -> str:
    """Mermaid Gantt chart of the timeline (real dates from the project start)."""
    clean = lambda s: s.replace(":", " -").replace("#", "").replace(";", ",")  # noqa: E731
    lines = ["gantt", f"    title {clean(model)} workflow", "    dateFormat YYYY-MM-DD", "    axisFormat %d %b"]
    n = 0
    for p in phases:
        lines.append(f"    section {clean(p['name'])[:40]}")
        for o in occurrences.get(p["name"], []):
            n += 1
            day = start + timedelta(days=round(o["start"] * 7))
            days = max(1, round((o["end"] - o["start"]) * 7))
            lines.append(f"    {clean(o['label'])[:30]} :t{n}, {day.isoformat()}, {days}d")
    return "\n".join(lines)


def project_start(today: date | None = None) -> date:
    """Timelines start on the next Monday."""
    today = today or date.today()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


def normalise_roles(names: list[str]) -> list[str]:
    """Map free-text role names from the LLM to catalog role ids where possible; keep the rest as written."""
    roles = get_catalog().roles
    out = []
    for n in names:
        key = n.strip().lower().replace("&", "and")
        match = next((r.id for r in roles if key in (r.id, r.name.lower()) or r.id.replace("_", " ") in key
                      or key.rstrip("s") in r.name.lower()), None)
        if match is None:
            match = {"security": "infosec", "information security": "infosec", "compliance": "compliance_legal",
                     "legal": "compliance_legal", "architect": "architect_developer", "developer": "architect_developer",
                     "risk": "risk_management", "operations": "operations", "auditor": "auditor_regulator",
                     "product owner": "product_owner", "project manager": "project_manager",
                     "business analyst": "business_analyst"}.get(next((k for k in (
                         "project manager", "product owner", "business analyst", "information security", "security",
                         "compliance", "legal", "architect", "developer", "risk", "operations", "auditor") if k in key), ""))
        if match and match not in out:
            out.append(match)
        elif not match and n not in out:
            out.append(n)
    return out
