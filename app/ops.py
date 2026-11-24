"""Deploy, monitor and improve (problem statement step 20).

Staged deployment
  advisory  the assistant runs alongside the business analysts. Its documents are watermarked "advisory", are not
            added to the knowledge base, and are compared with the analysts' own work (`compare_with_analyst`).
  assisted  documents generated after the human approval gates are the project's official artefacts.
New projects start in the system's stage. With `require_current_evaluation` on (the default), a project can only
start in "assisted" when an evaluation has PASSED under the current provenance fingerprint, i.e. after every
significant update (model, prompts, rules, embeddings, approved knowledge) the system must be re-evaluated.

Monitoring    `quality_monitor()` aggregates human corrections, overrides, compliance gaps found before and after
              approval, escalations and security events: the signals of incorrect recommendations.
Expansion     a planned domain is activated only with approved knowledge for it and a passing evaluation (or a
              recorded justification).
Accountability `accountability_pack()` bundles prompts and responses, retrieved evidence, agent decisions, user
              changes, approvals, artefact versions and evaluations for one project.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.audit import record, verify_chain
from app.catalog.loader import get_catalog
from app.db import SessionLocal
from app.models import (ApprovalRequest, Artifact, AuditLog, EvaluationRun, KbDocument, LlmCall, Project, Requirement,
                        RetrievalLog, ReviewItem, SystemSetting)

STAGES = ("advisory", "assisted")
DEFAULT_DEPLOYMENT = {"stage": "advisory", "require_current_evaluation": True}


# ---------- Settings ----------

def get_setting(key: str, default: dict) -> dict:
    with SessionLocal() as s:
        row = s.get(SystemSetting, key)
        return dict(row.value) if row else dict(default)


def set_setting(key: str, value: dict, by: str) -> dict:
    with SessionLocal.begin() as s:
        row = s.get(SystemSetting, key)
        if row is None:
            s.add(SystemSetting(key=key, value=value, updated_by=by))
        else:
            row.value, row.updated_by = value, by
    return value


# ---------- Re-evaluation after significant updates ----------

def current_fingerprint() -> tuple[str, dict]:
    from app.security.provenance import fingerprint, snapshot
    snap = snapshot()
    return fingerprint(snap), snap


def evaluation_status(domain: str | None = None) -> dict:
    fp, snap = current_fingerprint()
    with SessionLocal() as s:
        q = select(EvaluationRun).where(EvaluationRun.mode.like("automated%") | (EvaluationRun.mode == "human_review"))
        if domain:
            q = q.where(EvaluationRun.domain == domain)
        runs = s.scalars(q.order_by(EvaluationRun.id.desc())).all()
        passing = next((r for r in runs if r.passed and r.fingerprint == fp), None)
        last = runs[0] if runs else None
        changed = []
        if last and last.fingerprint != fp:
            old = last.provenance or {}
            for key in ("llm", "embedding_model", "reranker", "sdlc_rules"):
                if old.get(key) != snap.get(key):
                    changed.append(key)
            changed += [f"prompt:{k}" for k, v in snap["prompts"].items() if (old.get("prompts") or {}).get(k) != v]
            kb_old = {k for k in old.get("knowledge_base", []) if not k.startswith("project-")}
            kb_new = {k for k in snap["knowledge_base"] if not k.startswith("project-")}
            changed += [f"kb:+{k}" for k in sorted(kb_new - kb_old)] + [f"kb:-{k}" for k in sorted(kb_old - kb_new)]
    return {"fingerprint": fp, "current_evaluation_passed": passing is not None,
            "passing_run": {"id": passing.id, "case": passing.case_id, "at": passing.created_at.isoformat()} if passing else None,
            "last_run": {"id": last.id, "case": last.case_id, "passed": last.passed, "at": last.created_at.isoformat()} if last else None,
            "re_evaluation_required": passing is None, "changes_since_last_run": changed}


def stage_for_new_project(domain: str) -> tuple[str, str | None]:
    dep = get_setting("deployment", DEFAULT_DEPLOYMENT)
    if dep["stage"] == "assisted" and dep.get("require_current_evaluation", True) and \
            not evaluation_status(domain)["current_evaluation_passed"]:
        return "advisory", "no passing evaluation for the current model, prompts, rules and knowledge"
    return dep["stage"], None


# ---------- Domain expansion ----------

def domain_status(domain_id: str) -> str:
    override = get_setting("domain_status", {}).get(domain_id)
    if override:
        return override["status"]
    d = get_catalog().domain(domain_id)
    return d.status if d else "planned"


def domain_readiness(domain_id: str) -> dict:
    with SessionLocal() as s:
        docs = s.scalars(select(KbDocument).where(KbDocument.status == "active")).all()
    applicable = [d for d in docs if domain_id in (d.applicability or {}).get("domains", []) or
                  "all" in (d.applicability or {}).get("domains", [])]
    by_col = Counter(d.collection for d in applicable)
    specific = Counter(d.collection for d in applicable if domain_id in (d.applicability or {}).get("domains", []))
    ev = evaluation_status(domain_id)
    checks = {"process_knowledge": specific["glossary_process"] >= 1, "policies": by_col["policy_control"] >= 1,
              "passing_evaluation": ev["current_evaluation_passed"]}
    return {"domain": domain_id, "status": domain_status(domain_id), "checks": checks, "ready": all(checks.values()),
            "knowledge": dict(by_col)}


def set_domain(domain_id: str, active: bool, by: str, justification: str) -> dict:
    if get_catalog().domain(domain_id) is None:
        raise ValueError(f"Unknown domain '{domain_id}'")
    readiness = domain_readiness(domain_id)
    if active and not readiness["ready"] and len(justification.strip()) < 20:
        raise ValueError(f"Domain not ready ({[k for k, v in readiness['checks'].items() if not v]}); "
                         "activate only with a written justification of at least 20 characters")
    overrides = get_setting("domain_status", {})
    overrides[domain_id] = {"status": "active" if active else "planned", "by": by, "justification": justification,
                            "checks": readiness["checks"], "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    set_setting("domain_status", overrides, by)
    record(None, by, "domain_activated" if active else "domain_deactivated",
           {"domain": domain_id, "checks": readiness["checks"], "justification": justification})
    return domain_readiness(domain_id)


# ---------- Comparison with business analysts (advisory mode) ----------

def compare_with_analyst(graph, project_id: int, analyst: str, statements: list[str], threshold: float = 0.80) -> dict:
    from eval import metrics as M
    from eval.run import ai_requirements
    from app.security.provenance import fingerprint

    state = graph.get_state({"configurable": {"thread_id": f"project-{project_id}-v2"}}).values or {}
    ai = ai_requirements(state)
    if not ai:
        raise ValueError("The assistant has not produced requirements for this project yet")
    statements = [s.strip() for s in statements if s.strip()]
    sim = M.similarity_matrix(statements, [r["statement"] for r in ai])
    m = M.match(sim, threshold)
    scores = M.prf(len(m), len(ai) - len(m), len(statements) - len(m))
    report = {
        "analyst": analyst, "threshold": threshold, "analyst_requirements": len(statements), "ai_requirements": len(ai),
        "agreement": scores,  # precision = share of AI items the analyst also found; recall = share of analyst items AI found
        "matched": [{"analyst": statements[gi], "ai": ai[pi]["id"], "similarity": s} for gi, (pi, s) in sorted(m.items())],
        "only_analyst": [statements[i] for i in range(len(statements)) if i not in m],
        "only_ai": [{"id": r["id"], "statement": r["statement"]} for i, r in enumerate(ai) if i not in {p for p, _ in m.values()}],
    }
    prov = state.get("provenance", {})
    with SessionLocal.begin() as s:
        project = s.get(Project, project_id)
        s.add(EvaluationRun(case_id=f"project-{project_id}", domain=project.domain if project else None,
                            mode="shadow_comparison", project_id=project_id, fingerprint=fingerprint(prov) if prov else "",
                            provenance=prov, metrics=report, passed=None, created_by=analyst))
    record(project_id, analyst, "analyst_comparison", {"agreement": scores, "only_analyst": len(report["only_analyst"]),
                                                         "only_ai": len(report["only_ai"])})
    return report


# ---------- Monitoring incorrect recommendations and compliance gaps ----------

def quality_monitor() -> dict:
    with SessionLocal() as s:
        events = s.execute(select(AuditLog.action, AuditLog.detail, AuditLog.created_at)).all()
        crs = s.scalars(select(ApprovalRequest)).all()
        reviews = Counter(s.scalars(select(ReviewItem.status)).all())
    month = lambda t: t.strftime("%Y-%m")  # noqa: E731
    trend: dict[str, Counter] = defaultdict(Counter)
    totals = Counter()
    for action, detail, at in events:
        d = detail or {}
        m = trend[month(at)]
        if action == "baseline_approve":
            for e in d.get("edits", []):
                totals[f"requirement_{e['action']}"] += 1
                m[f"requirement_{e['action']}"] += 1
        elif action == "legal_interpretations_decided":
            for k in ("accept", "modify", "reject"):
                totals[f"interpretation_{k}"] += d.get(k, 0)
                m[f"interpretation_{k}"] += d.get(k, 0)
        elif action == "sdlc_approve" and d.get("override_of_recommendation"):
            totals["sdlc_override"] += 1
            m["sdlc_override"] += 1
        elif action == "sdlc_approve":
            totals["sdlc_accept"] += 1
        elif action in ("workflow_modified", "clarification_regenerate", "baseline_regenerate", "sdlc_regenerate",
                        "workflow_regenerate", "injection_neutralised", "llm_filtered", "agent_permission_denied",
                        "readiness_no_go"):
            totals[action] += 1
            m[action] += 1
        elif action == "mapped_compliance":
            totals["compliance_gaps_found_by_agent"] += d.get("gaps", 0)
            m["compliance_gaps_found_by_agent"] += d.get("gaps", 0)
        elif action == "grounded_requirements":
            totals["escalated_requirements"] += d.get("escalated", 0)
    regulated = {"regulatory", "privacy", "audit"}
    late_gaps = [c for c in crs if c.kind == "change_request" and c.status == "applied"
                 and regulated & set((c.payload.get("impact") or {}).get("categories", []))]
    decided = totals["requirement_accept"] + totals["requirement_modify"] + totals["requirement_reject"]
    interp = totals["interpretation_accept"] + totals["interpretation_modify"] + totals["interpretation_reject"]
    sdlc = totals["sdlc_accept"] + totals["sdlc_override"]
    return {
        "requirement_correction_rate": round((totals["requirement_modify"] + totals["requirement_reject"]) / decided, 3) if decided else None,
        "interpretation_correction_rate": round((totals["interpretation_modify"] + totals["interpretation_reject"]) / interp, 3) if interp else None,
        "sdlc_override_rate": round(totals["sdlc_override"] / sdlc, 3) if sdlc else None,
        "compliance_gaps_found_by_agent": totals["compliance_gaps_found_by_agent"],
        "compliance_gaps_found_after_approval": len(late_gaps),
        "kb_answers": {"corrected": reviews.get("corrected", 0), "dismissed": reviews.get("dismissed", 0),
                       "confirmed": reviews.get("confirmed", 0), "open": reviews.get("open", 0)},
        "totals": dict(totals),
        "trend": {k: dict(v) for k, v in sorted(trend.items())},
    }


# ---------- Accountability ----------

def accountability_pack(graph, project_id: int) -> dict:
    """Everything needed to audit one project: prompts and responses, evidence, decisions, changes, approvals,
    artefact versions, evaluations and provenance."""
    state = graph.get_state({"configurable": {"thread_id": f"project-{project_id}-v2"}}).values or {}
    with SessionLocal() as s:
        p = s.get(Project, project_id)
        out = {
            "project": {"id": p.id, "name": p.name, "domain": p.domain, "jurisdiction": p.jurisdiction, "status": p.status,
                        "deployment_stage": p.deployment_stage, "legal_hold": p.legal_hold},
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "audit_chain": verify_chain(),
            "provenance": state.get("provenance", {}),
            "audit_log": [{"at": a.created_at.isoformat(), "actor": a.actor, "principal": a.principal, "action": a.action,
                           "detail": a.detail, "hash": a.hash} for a in
                          s.scalars(select(AuditLog).where(AuditLog.project_ref == project_id).order_by(AuditLog.id))],
            "llm_calls": [{"at": c.created_at.isoformat(), "agent": c.agent, "purpose": c.purpose, "model": c.model,
                           "schema": c.schema, "prompt": c.prompt, "response": c.response, "prompt_sha256": c.prompt_sha256,
                           "tokens": {"input": c.input_tokens, "cached": c.cached_tokens, "output": c.output_tokens},
                           "cost_usd": c.cost_usd, "latency_ms": c.latency_ms, "filtered": c.filtered}
                          for c in s.scalars(select(LlmCall).where(LlmCall.project_ref == project_id).order_by(LlmCall.id))],
            "retrieved_evidence": [{"at": r.created_at.isoformat(), "agent": r.agent, "queries": r.queries, "filters": r.filters,
                                    "hits": r.hits} for r in
                                   s.scalars(select(RetrievalLog).where(RetrievalLog.project_ref == project_id).order_by(RetrievalLog.id))],
            "requirements": [{"req_id": r.req_id, "statement": r.statement, "status": r.approval_status, "version": r.version,
                              "history": r.history, "citations": r.citations} for r in
                             s.scalars(select(Requirement).where(Requirement.project_id == project_id))],
            "decisions_in_graph": {"baseline": state.get("baseline_approvals", []), "sdlc": state.get("sdlc_approvals", []),
                                   "workflow": state.get("workflow_approvals", []),
                                   "requirement_decisions": {r["id"]: r.get("decision") for r in state.get("requirements", []) if r.get("decision")},
                                   "legal_decisions": {m.get("id"): m.get("legal_decision") for m in
                                                       state.get("compliance", {}).get("mappings", []) if m.get("legal_decision")}},
            "approval_requests": [{"id": a.id, "kind": a.kind, "title": a.title, "status": a.status, "payload": a.payload,
                                   "decisions": a.decisions} for a in
                                  s.scalars(select(ApprovalRequest).where(ApprovalRequest.project_id == project_id))],
            "artefact_versions": [{"kind": a.kind, "version": a.version, "status": a.status, "created_at": a.created_at.isoformat(),
                                   "superseded_at": a.superseded_at.isoformat() if a.superseded_at else None, "content": a.content["data"]}
                                  for a in s.scalars(select(Artifact).where(Artifact.project_id == project_id)
                                                     .order_by(Artifact.version, Artifact.kind))],
            "evaluations": [{"id": e.id, "mode": e.mode, "passed": e.passed, "fingerprint": e.fingerprint, "metrics": e.metrics,
                             "at": e.created_at.isoformat()} for e in
                            s.scalars(select(EvaluationRun).where(EvaluationRun.project_id == project_id))],
        }
    out["summary"] = {k: len(v) for k, v in out.items() if isinstance(v, list)}
    return out


def usage(project_id: int | None = None) -> dict:
    with SessionLocal() as s:
        q = select(LlmCall.agent, LlmCall.model, func.count(), func.sum(LlmCall.input_tokens), func.sum(LlmCall.cached_tokens),
                   func.sum(LlmCall.output_tokens), func.sum(LlmCall.cost_usd)).group_by(LlmCall.agent, LlmCall.model)
        if project_id is not None:
            q = q.where(LlmCall.project_ref == project_id)
        rows = s.execute(q).all()
    by = [{"agent": a, "model": m, "calls": n, "input_tokens": int(i or 0), "cached_tokens": int(c or 0),
           "output_tokens": int(o or 0), "cost_usd": round(float(cost or 0), 4)} for a, m, n, i, c, o, cost in rows]
    return {"calls": sum(r["calls"] for r in by), "input_tokens": sum(r["input_tokens"] for r in by),
            "output_tokens": sum(r["output_tokens"] for r in by), "cost_usd": round(sum(r["cost_usd"] for r in by), 4),
            "by_agent_model": sorted(by, key=lambda r: -r["cost_usd"])}
