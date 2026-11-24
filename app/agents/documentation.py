"""Documentation agent: persists the approved baseline and generates the requirement artefacts.

Standard (step 12): the eleven artefacts in standards.ARTEFACTS: SRS, user stories, use cases, process workflows,
data requirements, interface requirements, threat and risk register, compliance-control matrix, RTM, assumptions and
dependency register, and open issues. Plus the requirements in the step-8 standard structure and the SDLC decision.
Every row carries a `trace` (or the RTM's source columns) linking it to the original stakeholder statement (source
quote) and supporting document (source title, id and hash, plus KB citations).
"""

from sqlalchemy import delete, select

from app import llm
from app.agents.common import domain_name, format_requirements, role_name
from app.agents.sdlc import baseline
from app.agents.standards import standard_record, trace
from app.audit import record
from app.catalog.loader import get_catalog
from app.db import SessionLocal
from app.graph.state import ProjectState
from app.kb.lookup import in_force
from app.models import Artifact, Project, Requirement, Source
from app.schemas import UseCasesResult, UserStoriesResult

STORIES_PROMPT = """Write one user story per functional requirement of a {domain} system, using the most relevant
user role (customer, credit officer, compliance officer, ...). Each story needs 2-4 Given/When/Then acceptance
criteria consistent with the requirement. Use the requirement IDs exactly as given.
{template}

Functional requirements:
{requirements}"""

USE_CASES_PROMPT = """Group the functional requirements of a {domain} system into use cases (at most 8). For each:
primary actor, preconditions, main success scenario as numbered steps, alternative flows, exception flows
(e.g. timeouts, validation failures, fraud flags), postconditions, and the requirement IDs it realises.
Number them UC-01, UC-02, ... Use the requirement IDs exactly as given.
{template}

Functional requirements:
{requirements}"""


TEMPLATE_KEYS = ("template-srs", "template-user-story", "template-use-case")


def _template(doc_key: str) -> str:
    doc = in_force(doc_key)
    return f"Follow this template (v{doc.version}):\n{doc.content[:2000]}" if doc else ""


def _feed_project_history(state: ProjectState, srs: str) -> str | None:
    """Add the approved SRS to the knowledge base so future projects can learn from it (step 5)."""
    from datetime import date

    from app.kb.ingest import ItemMetadata, KbError, submit
    from app.kb.lifecycle import approve
    from app.llm import LLMNotConfiguredError

    pid = state["project_id"]
    approver = next((a for a in reversed(state.get("baseline_approvals", [])) if a["decision"] == "approve"), None)
    try:
        doc, _ = submit(ItemMetadata(
            doc_key=f"project-{pid}-srs", collection="project_history", title=f"Approved SRS — project {pid}",
            issuer="Requirements Desk (approved project)", license="internal", jurisdictions=[state.get("jurisdiction", "IN")],
            effective_from=date.today(), version=f"{date.today().isoformat()}-it{state.get('iteration', 1)}",
            applicability={"domains": [state["domain"]]}, content_format="markdown"), srs, "documentation_agent")
        approve(doc.id, approver["reviewer"] if approver else "documentation_agent", "product_owner")
        return doc.version
    except (KbError, LLMNotConfiguredError) as exc:
        record(pid, "documentation_agent", "project_history_skipped", {"reason": str(exc)})
        return None


def _traces(ids: list[str], by_id: dict[str, dict]) -> list[dict]:
    return [trace(by_id[i]) for i in ids if i in by_id]


def _mermaid_label(text: str) -> str:
    return text.replace('"', "'").replace("\n", " ")[:80]


def process_workflows(use_cases: list[dict], by_id: dict[str, dict]) -> list[dict]:
    """One process flow per use case: main steps, with alternative and exception branches (Mermaid)."""
    flows = []
    for u in use_cases:
        lines = ["flowchart TD", f'    S(["{_mermaid_label(u["primary_actor"])} starts: {_mermaid_label(u["title"])}"])']
        prev = "S"
        for i, step in enumerate(u["main_flow"], 1):
            lines.append(f'    M{i}["{i}. {_mermaid_label(step)}"]')
            lines.append(f"    {prev} --> M{i}")
            prev = f"M{i}"
        lines.append(f'    E(["{_mermaid_label("; ".join(u["postconditions"]) or "Done")}"])')
        lines.append(f"    {prev} --> E")
        anchor = "M1" if u["main_flow"] else "S"
        for j, alt in enumerate(u["alternative_flows"], 1):
            lines.append(f'    A{j}["Alt: {_mermaid_label(alt)}"]')
            lines.append(f"    {anchor} -.-> A{j} -.-> E")
        for j, exc in enumerate(u["exception_flows"], 1):
            lines.append(f'    X{j}["Exception: {_mermaid_label(exc)}"]')
            lines.append(f"    {prev} -. fails .-> X{j}")
        flows.append({"id": f"PF-{u['id'].split('-')[-1]}", "use_case": u["id"], "title": u["title"],
                      "actor": u["primary_actor"], "mermaid": "\n".join(lines),
                      "requirement_ids": u["requirement_ids"], "trace": _traces(u["requirement_ids"], by_id)})
    return flows


def data_requirements(reqs: list[dict], compliance: dict, sources: list[dict]) -> list[dict]:
    """Requirements about data and privacy, with retention obligations and the source's sensitivity."""
    obligations = compliance.get("retention_and_reporting", [])
    sensitivity = {s["id"]: s["sensitivity"] for s in sources}
    return [{"req_id": r["id"], "statement": r["statement"], "categories": r["categories"],
             "retention": [f"{o['period']} ({o['regulation']})" for o in obligations
                           if o["req_id"] == r["id"] and o["kind"] == "data_retention" and o["period"]],
             "regulations": r.get("applicable_regulations", []), "source_sensitivity": sensitivity.get(r.get("source_id")),
             "trace": trace(r)}
            for r in reqs if {"data", "privacy"} & set(r["categories"])]


def interface_requirements(reqs: list[dict]) -> list[dict]:
    """Integration requirements: the external systems and interfaces the system must work with."""
    return [{"req_id": r["id"], "statement": r["statement"], "dependencies": [*r.get("depends_on", []), *r.get("dependencies", [])],
             "acceptance_criteria": r["acceptance_criteria"], "trace": trace(r)}
            for r in reqs if "integration" in r["categories"]]


def threat_risk_register(state: ProjectState, accepted: set[str], by_id: dict[str, dict]) -> list[dict]:
    """Risks from the risk-analysis agent plus threats (security & privacy findings) with their controls."""
    rows = [rk | {"entry": "risk", "trace": _traces(rk["related_req_ids"], by_id)} for rk in state.get("risks", [])]
    for n, f in enumerate(state.get("security_findings", []), 1):
        control = f"SUG-SEC-{n:03d}"
        rows.append({"entry": "threat", "id": f"THR-{n:02d}", "title": f["description"][:80], "type": f["kind"],
                     "description": f["description"], "level": f["severity"], "mitigation": f["suggested_requirement"],
                     "control_requirement": control if control in accepted else None,
                     "related_req_ids": [f["req_id"]] if f.get("req_id") else [],
                     "citation": f.get("citation"), "trace": _traces([f["req_id"]] if f.get("req_id") else [], by_id)})
    return rows


def assumptions_dependencies(reqs: list[dict]) -> list[dict]:
    rows = []
    for r in reqs:
        rows += [{"kind": "assumption", "text": a, "req_id": r["id"], "trace": trace(r)} for a in r.get("assumptions", [])]
        rows += [{"kind": "dependency", "text": d, "on_requirement": True, "req_id": r["id"], "trace": trace(r)}
                 for d in r.get("depends_on", [])]
        rows += [{"kind": "dependency", "text": d, "on_requirement": False, "req_id": r["id"], "trace": trace(r)}
                 for d in r.get("dependencies", [])]
    counters = {"assumption": 0, "dependency": 0}
    for row in rows:
        counters[row["kind"]] += 1
        row["id"] = f"{'ASM' if row['kind'] == 'assumption' else 'DEP'}-{counters[row['kind']]:02d}"
    return rows


def persist_baseline(state: ProjectState) -> ProjectState:
    pid = state["project_id"]
    reqs = baseline(state)
    with SessionLocal.begin() as session:
        session.execute(delete(Requirement).where(Requirement.project_id == pid))
        session.add_all(
            Requirement(project_id=pid, req_id=r["id"], statement=r["statement"], req_type=r["type"],
                        categories=r["categories"], priority=r["priority"],
                        acceptance_criteria=r["acceptance_criteria"], source_quote=r.get("source_quote", ""),
                        confidence=r["confidence"], approval_status=r["status"], origin=r.get("origin", "extracted"),
                        source_id=r.get("source_id"), stakeholder_role=r.get("stakeholder_role"),
                        source_type=r.get("source_type"), grounding_support=r.get("grounding_support"),
                        citations=r.get("citations", []), business_justification=r.get("business_justification", ""),
                        assumptions=r.get("assumptions", []),
                        dependencies=[*r.get("depends_on", []), *r.get("dependencies", [])],
                        applicable_regulations=r.get("applicable_regulations", []), risk_level=r.get("risk_level", "low"),
                        version=r.get("version", 1), history=r.get("history", []))
            for r in reqs
        )
        session.get(Project, pid).status = "baselined"
    record(pid, "documentation_agent", "baseline_persisted", {"requirements": len(reqs)})
    return {}


def _srs(state: ProjectState, reqs: list[dict], stories: list[dict], use_cases: list[dict]) -> str:
    catalog = get_catalog()
    domain = catalog.domain(state["domain"])
    decision = state["sdlc_decision"]
    rec = next((s for s in state["sdlc_recommendations"] if s["model"] == decision["model"]), None)
    L = [f"# Software Requirements Specification — Project {state['project_id']}", "",
         f"**Domain:** {domain_name(state['domain'])}  ", f"**Approved SDLC model:** {decision['model']}", ""]
    L += ["## 1. Introduction", "",
          "This SRS was produced by the multi-agent requirements system from masked stakeholder sources and approved by: "
          + ", ".join(f"{role_name(a['role'])} ({a['reviewer']})" for a in state.get("baseline_approvals", []) if a["decision"] == "approve") + ".", ""]
    if domain:
        L += ["**Regulations assessed (confirm applicability with compliance):** " + "; ".join(domain.typical_regulations), ""]
    L += ["## 2. Stakeholders and sources", ""]
    L += [f"- **{s['title']}** — {catalog.source(s['source_type']).name if catalog.source(s['source_type']) else s['source_type']}, "
          f"{role_name(s['stakeholder_role'])}, sensitivity: {s['sensitivity']}" for s in state["sources"]]
    for title, kind in (("3. Functional requirements", "functional"), ("4. Non-functional requirements", "non_functional")):
        L += ["", f"## {title}", ""]
        for r in (x for x in reqs if x["type"] == kind):
            L.append(f"### {r['id']} ({r['priority']})")
            L.append(r["statement"])
            L.append(f"*Categories:* {', '.join(r['categories'])} · *Source:* {r['source_title']} "
                     f"({role_name(r.get('stakeholder_role')) if r.get('origin') == 'extracted' else r.get('origin')}) · *Status:* {r['status']}"
                     f" · *Risk:* {r.get('risk_level', 'low')} · *Confidence:* {r['confidence']:.2f}")
            if r.get("business_justification"):
                L.append(f"*Justification:* {r['business_justification']}")
            deps = [*r.get("depends_on", []), *r.get("dependencies", [])]
            if deps or r.get("assumptions"):
                L.append(f"*Depends on:* {'; '.join(deps) or '—'} · *Assumes:* {'; '.join(r.get('assumptions', [])) or '—'}")
            if r.get("applicable_regulations"):
                L.append(f"*Regulations:* {'; '.join(r['applicable_regulations'])}")
            if r.get("citations"):
                L.append("*Grounded in:* " + "; ".join(f"{c['citation']} [{c['ref']}]" for c in r["citations"])
                         + f" · *{r.get('grounding_support', '').replace('_', ' ')}*")
            elif r.get("grounding_support") and r["grounding_support"] != "no_obligation_expected":
                L.append(f"*Grounding:* {r['grounding_support'].replace('_', ' ')} (reviewed by an approver)")
            L.extend(f"- [ ] {ac}" for ac in r["acceptance_criteria"])
            L.append("")
    if stories:
        L += ["## 5. User stories", ""]
        L += [f"- **{s['req_id']}** As a {s['as_a']}, I want {s['i_want']}, so that {s['so_that']}." for s in stories]
        L.append("")
    if use_cases:
        L += ["## 6. Use cases", ""]
        for u in use_cases:
            L += [f"### {u['id']} {u['title']}", f"*Actor:* {u['primary_actor']} · *Realises:* {', '.join(u['requirement_ids'])}", ""]
            L += [f"{i}. {step}" for i, step in enumerate(u["main_flow"], 1)]
            if u["exception_flows"]:
                L += ["", "*Exceptions:* " + "; ".join(u["exception_flows"])]
            L.append("")
    L += ["## 7. SDLC recommendation", ""]
    L += [f"{i}. **{s['model']}** — {s['score']}% ({', '.join(s['key_drivers'])})" for i, s in enumerate(state["sdlc_recommendations"], 1)]
    L += ["", f"Selected: **{decision['model']}**" + (f" ({rec['score']}%)" if rec else ""), ""]
    if state.get("sdlc_explanation"):
        L += [state["sdlc_explanation"]["summary"], ""]
    wf = state.get("sdlc_workflow")
    if wf:
        sched = wf.get("schedule", {})
        L += ["## 8. Project SDLC workflow", "", f"*Cadence:* {wf['cadence']}",
              f"*Timeline:* {sched.get('total_weeks', '?')} weeks from {sched.get('start_date', '?')}", ""]
        if wf.get("gantt"):
            L += ["```mermaid", wf["gantt"], "```", ""]
        if wf.get("component_plan"):
            L += ["**How each component runs in this project**", ""]
            L += [f"- **{c['component'].capitalize()}:** {c['how']}" for c in wf["component_plan"]] + [""]
        for i, ph in enumerate(wf["phases"], 1):
            g = ph["approval_gate"]
            L += [f"### 8.{i} {ph['name']}", ph["objective"], "",
                  f"- **When:** {ph.get('timing', '—')}",
                  f"- **Activities:** {'; '.join(ph['activities'])}",
                  f"- **Roles:** {', '.join(ph['responsible_roles'])}",
                  f"- **Deliverables:** {'; '.join(ph['deliverables'])}",
                  f"- **Security:** {'; '.join(ph['security_activities']) or '—'}",
                  f"- **Testing:** {'; '.join(ph['testing']) or '—'}",
                  f"- **Compliance checkpoints:** {'; '.join(ph['compliance_checkpoints']) or '—'}",
                  f"- **Entry criteria:** {'; '.join(ph['entry_criteria']) or '—'}",
                  f"- **Exit criteria:** {'; '.join(ph['exit_criteria']) or '—'}",
                  f"- **Traceability:** {'; '.join(ph.get('traceability', [])) or '—'}",
                  f"- **Human approval gate — {g['name']}:** {', '.join(role_name(a) for a in g['approvers'])} · {'; '.join(g['criteria'])}", ""]
    data_reqs = [r for r in reqs if {"data", "privacy"} & set(r["categories"])]
    if data_reqs:
        L += ["## 9. Data requirements", ""] + [f"- **{r['id']}** {r['statement']}" for r in data_reqs] + [""]
    iface = [r for r in reqs if "integration" in r["categories"]]
    if iface:
        L += ["## 10. Interface requirements", ""] + [f"- **{r['id']}** {r['statement']}" for r in iface] + [""]
    assumptions = [(r["id"], a) for r in reqs for a in r.get("assumptions", [])]
    if assumptions:
        L += ["## 11. Assumptions", ""] + [f"- {a} (*{rid}*)" for rid, a in assumptions] + [""]
    if state.get("risks"):
        L += ["## 12. Key risks", ""] + [f"- **{r['id']}** {r['title']} — {r['level']} ({r['score']}): {r['mitigation']}"
                                        for r in state["risks"][:8]] + [""]
    return "\n".join(L)


def documentation(state: ProjectState) -> ProjectState:
    pid = state["project_id"]
    reqs = baseline(state)
    functional = [r for r in reqs if r["type"] == "functional"]
    stories = []
    if functional:
        result = llm.structured(UserStoriesResult, STORIES_PROMPT.format(
            domain=domain_name(state["domain"]), requirements=format_requirements(functional),
            template=_template("template-user-story")))
        ids = {r["id"] for r in functional}
        stories = [s.model_dump() for s in result.stories if s.req_id in ids]
    use_cases = []
    if functional:
        uc = llm.structured(UseCasesResult, USE_CASES_PROMPT.format(
            domain=domain_name(state["domain"]), requirements=format_requirements(functional),
            template=_template("template-use-case")))
        ids = {r["id"] for r in functional}
        use_cases = [u.model_dump() | {"requirement_ids": [i for i in u.requirement_ids if i in ids]} for u in uc.use_cases]

    with SessionLocal() as session:
        hashes = dict(session.execute(select(Source.id, Source.content_sha256).where(Source.project_id == pid)).all())
    mappings = state.get("compliance", {}).get("mappings", [])
    approvers = [f"{role_name(a['role'])} ({a['reviewer']})" for a in state.get("baseline_approvals", []) if a["decision"] == "approve"]
    by_id = {r["id"]: r for r in reqs}
    rtm = [{
        "req_id": r["id"], "statement": r["statement"], "type": r["type"], "priority": r["priority"], "status": r["status"],
        "categories": r["categories"], "business_justification": r.get("business_justification", ""),
        "dependencies": [*r.get("depends_on", []), *r.get("dependencies", [])], "assumptions": r.get("assumptions", []),
        "risk_level": r.get("risk_level", "low"), "source_quote": r.get("source_quote", ""),
        "origin": r.get("origin", "extracted"), "stakeholder_role": r.get("stakeholder_role"),
        "source_title": r.get("source_title"), "source_type": r.get("source_type"), "source_id": r.get("source_id"),
        "source_sha256": hashes.get(r.get("source_id")),
        "regulations": sorted({m["regulation"] for m in mappings if m["req_id"] == r["id"]
                               and (m.get("legal_decision") or {}).get("action") != "reject"}),
        "citations": [c["citation"] for c in r.get("citations", [])],
        "grounding_support": r.get("grounding_support"), "confidence": r["confidence"],
        "escalated": bool(r.get("escalated")),
        "risks": [rk["id"] for rk in state.get("risks", []) if r["id"] in rk["related_req_ids"]],
        "user_story": any(s["req_id"] == r["id"] for s in stories),
        "use_cases": [u["id"] for u in use_cases if r["id"] in u["requirement_ids"]],
        "sdlc_phase": next((ph["name"] for ph in state.get("sdlc_workflow", {}).get("phases", []) if r["id"] in ph["requirement_ids"]), None),
        "tests": len(r["acceptance_criteria"]),
        "approved_by": approvers,
    } for r in reqs]
    accepted = {r["id"] for r in reqs}
    gaps = state.get("compliance", {}).get("gaps", [])
    comp = state.get("compliance", {})
    compliance_matrix = {
        "mappings": [m | {"trace": trace(by_id[m["req_id"]])} for m in mappings if m["req_id"] in accepted],
        "gaps": [g | {"addressed_by": f"SUG-CMP-{n:03d}" if f"SUG-CMP-{n:03d}" in accepted else None}
                 for n, g in enumerate(gaps, 1)],
        "checkpoints": comp.get("checkpoints", []),
        "retention_and_reporting": [o for o in comp.get("retention_and_reporting", []) if o["req_id"] in accepted],
        "determination": comp.get("determination"),
        "evidence": comp.get("evidence", []),
    }
    issue_ids = lambda x: [i.strip() for i in (x or "").split(",") if i.strip()]  # noqa: E731
    open_issues = [q | {"trace": _traces(q["related_req_ids"], by_id)} for q in state.get("clarifications", [])] + \
        [i | {"trace": _traces(issue_ids(i["req_id"]), by_id)} for i in state.get("issues", [])
         if i["severity"] == "high" and i["type"] != "clarification_needed"]
    srs = _srs(state, reqs, stories, use_cases)
    kb_versions = {k: (d.version if (d := in_force(k)) else None) for k in TEMPLATE_KEYS}
    artifacts = {
        "srs_markdown": srs,
        "kb_versions": kb_versions | {"sdlc_rules": state.get("sdlc_rules_version"),
                                      "evidence": sorted({e["doc_key"] + "@" + e["version"]
                                                          for e in state.get("compliance", {}).get("evidence", [])})},
        "requirements": [standard_record(r) for r in reqs],
        "provenance": state.get("provenance", {}),
        "user_stories": [s | {"trace": _traces([s["req_id"]], by_id)} for s in stories],
        "use_cases": [u | {"trace": _traces(u["requirement_ids"], by_id)} for u in use_cases],
        "process_workflows": process_workflows(use_cases, by_id),
        "data_requirements": data_requirements(reqs, comp, state.get("sources", [])),
        "interface_requirements": interface_requirements(reqs),
        "sdlc_workflow": state.get("sdlc_workflow", {}),
        "traceability_matrix": rtm,
        "compliance_matrix": compliance_matrix,
        "risk_register": state.get("risks", []),
        "threat_risk_register": threat_risk_register(state, accepted, by_id),
        "assumptions_dependencies": assumptions_dependencies(reqs),
        "open_issues": open_issues,
        "sdlc": {"decision": state["sdlc_decision"], "recommendations": state["sdlc_recommendations"],
                 "factors": state["factors"], "factor_signals": state.get("factor_signals", {}),
                 "characteristics": state.get("sdlc_characteristics", []), "rules_version": state.get("sdlc_rules_version"),
                 "rules_fired": state.get("sdlc_rules_fired", []),
                 "explanation": state.get("sdlc_explanation", {}), "approvals": state.get("sdlc_approvals", [])},
    }
    from datetime import datetime, timezone

    from sqlalchemy import func, update
    with SessionLocal.begin() as session:
        project = session.get(Project, pid)
        advisory = project.deployment_stage == "advisory"
        if advisory:  # step 20: advisory outputs are for comparison only, never official documents
            artifacts["srs_markdown"] = ("> **ADVISORY OUTPUT.** Produced while the assistant runs in advisory mode, for comparison "
                                         "with the business analysts' own analysis. Not an approved document.\n\n" + artifacts["srs_markdown"])
        version = (session.scalar(select(func.max(Artifact.version)).where(Artifact.project_id == pid)) or 0) + 1
        session.execute(update(Artifact).where(Artifact.project_id == pid, Artifact.superseded_at.is_(None))
                        .values(superseded_at=datetime.now(timezone.utc)))
        session.add_all(Artifact(project_id=pid, kind=k, content={"data": v}, version=version,
                                 status="advisory" if advisory else "approved") for k, v in artifacts.items())
        project.status = "completed"
    history_version = None if advisory else _feed_project_history(state, srs)
    record(pid, "documentation_agent", "artifacts_generated",
           {"kinds": list(artifacts), "requirements": len(reqs), "user_stories": len(stories), "use_cases": len(use_cases),
            "project_history_version": history_version, "artifact_version": version, "advisory": advisory})
    return {"artifacts": artifacts}
