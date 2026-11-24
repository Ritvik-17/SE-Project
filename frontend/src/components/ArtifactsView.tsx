import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import { api, type Artifacts, type Trace } from "../api";
import { useCatalog } from "../catalog";
import Diagram from "./Diagram";
import WorkflowView from "./WorkflowView";

// Step 12 artefacts (app/agents/standards.py ARTEFACTS), plus the step-8 requirement register and the SDLC workflow.
const VIEWS = ["SDLC workflow", "SRS", "Requirements", "User stories", "Use cases", "Process workflows", "Data requirements",
  "Interface requirements", "Threat & risk register", "Compliance matrix", "Traceability matrix", "Assumptions & dependencies",
  "Open issues"] as const;

/** Link from an artefact row back to the stakeholder statement and supporting document. */
function TraceCell({ t }: { t: Trace | Trace[] | undefined }) {
  const list = Array.isArray(t) ? t : t ? [t] : [];
  if (!list.length) return <span className="muted">—</span>;
  return (
    <>{list.map((x) => (
      <div key={x.req_id} className="small trace">
        <code>{x.req_id}</code> {x.source_title ?? "agent suggestion"}
        {x.source_quote && <div className="quote">“{x.source_quote}”</div>}
        {x.citations.length > 0 && <div className="muted">{x.citations.join("; ")}</div>}
      </div>
    ))}</>
  );
}

export default function ArtifactsView({ projectId }: { projectId: number }) {
  const catalog = useCatalog();
  const [a, setA] = useState<Artifacts | null>(null);
  const [view, setView] = useState<(typeof VIEWS)[number]>("SDLC workflow");

  useEffect(() => {
    api.artifacts(projectId).then(setA);
  }, [projectId]);

  if (!a) return <p className="muted">Loading documents…</p>;

  function download(name: string, content: string, type = "text/markdown") {
    const url = URL.createObjectURL(new Blob([content], { type }));
    const link = Object.assign(document.createElement("a"), { href: url, download: name });
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="stack">
      <section className="row between">
        <div>
          <h2>Generated documents</h2>
          <p className="muted small">Approved SDLC model: <strong>{a.sdlc.decision.model}</strong> · {a.traceability_matrix.length} baselined requirements</p>
        </div>
        <div className="row">
          <button onClick={() => download(`srs-project-${projectId}.md`, a.srs_markdown)}>Download SRS (.md)</button>
          <button onClick={() => download(`artifacts-project-${projectId}.json`, JSON.stringify(a, null, 2), "application/json")}>All (.json)</button>
        </div>
      </section>
      <div className="tabs sub">
        {VIEWS.map((v) => <button key={v} className={view === v ? "active" : ""} onClick={() => setView(v)}>{v}</button>)}
      </div>
      {view === "SDLC workflow" && <WorkflowView workflow={a.sdlc_workflow} />}
      {view === "SRS" && <section className="card markdown"><Markdown>{a.srs_markdown}</Markdown></section>}
      {view === "Use cases" && (
        <div className="stack">
          {a.use_cases.length === 0 && <div className="empty">No functional requirements to model as use cases.</div>}
          {a.use_cases.map((u) => (
            <section key={u.id} className="card">
              <div className="section-head"><h3><code>{u.id}</code> {u.title}</h3><span className="small muted">Actor: {u.primary_actor}</span></div>
              <div className="phase-grid">
                <dl><dt>Preconditions</dt><dd><ul>{u.preconditions.map((x) => <li key={x}>{x}</li>)}</ul></dd></dl>
                <dl><dt>Main flow</dt><dd><ol style={{ margin: 0, paddingLeft: "1.1rem" }}>{u.main_flow.map((x) => <li key={x}>{x}</li>)}</ol></dd></dl>
                <dl><dt>Alternative flows</dt><dd><ul>{u.alternative_flows.map((x) => <li key={x}>{x}</li>)}</ul>{u.alternative_flows.length === 0 && "—"}</dd></dl>
                <dl><dt>Exceptions</dt><dd><ul>{u.exception_flows.map((x) => <li key={x}>{x}</li>)}</ul>{u.exception_flows.length === 0 && "—"}</dd></dl>
                <dl><dt>Postconditions</dt><dd><ul>{u.postconditions.map((x) => <li key={x}>{x}</li>)}</ul></dd></dl>
                <dl><dt>Realises</dt><dd>{u.requirement_ids.map((x) => <code key={x} style={{ marginRight: 6 }}>{x}</code>)}</dd></dl>
              </div>
            </section>
          ))}
        </div>
      )}
      {view === "Requirements" && (
        <section className="card table-scroll">
          <p className="note">The baseline in the standard requirement structure (step 8).</p>
          <table>
            <thead><tr><th>ID</th><th>Requirement</th><th>Category</th><th>Stakeholder</th><th>Justification</th><th>Prio</th>
              <th>Dependencies</th><th>Assumptions</th><th>Acceptance criteria</th><th>Regulations</th><th>Risk</th><th>Conf.</th><th>Approval</th></tr></thead>
            <tbody>{a.requirements.map((r) => (
              <tr key={r.id}>
                <td><code>{r.id}</code></td><td className="small">{r.statement}</td><td className="small">{r.categories.join(", ")}</td>
                <td className="small">{r.source_stakeholder ? catalog.role[r.source_stakeholder]?.name ?? r.source_stakeholder.replace(/_/g, " ") : "—"}</td>
                <td className="small">{r.business_justification || "—"}</td><td><span className={`tag prio-${r.priority}`}>{r.priority}</span></td>
                <td className="small">{r.dependencies.join("; ") || "—"}</td><td className="small">{r.assumptions.join("; ") || "—"}</td>
                <td className="small">{r.acceptance_criteria.length ? <ul>{r.acceptance_criteria.map((c) => <li key={c}>{c}</li>)}</ul> : "—"}</td>
                <td className="small">{r.applicable_regulations.join("; ") || "—"}</td>
                <td><span className={`tag sev-${r.risk_level}`}>{r.risk_level}</span></td><td className="num">{r.confidence.toFixed(2)}</td>
                <td><span className={`tag st-${r.approval_status}`}>{r.approval_status}</span></td>
              </tr>
            ))}</tbody>
          </table>
        </section>
      )}
      {view === "Process workflows" && (
        <div className="stack">
          {a.process_workflows.length === 0 && <div className="empty">No use cases, so no process flows.</div>}
          {a.process_workflows.map((f) => (
            <section key={f.id} className="card">
              <div className="section-head"><h3><code>{f.id}</code> {f.title}</h3><span className="small muted">from {f.use_case} · actor: {f.actor}</span></div>
              <Diagram code={f.mermaid} />
              <TraceCell t={f.trace} />
            </section>
          ))}
        </div>
      )}
      {view === "Data requirements" && (
        <section className="card table-scroll">
          {a.data_requirements.length === 0 ? <div className="empty">No data or privacy requirements in the baseline.</div> : (
            <table><thead><tr><th>Req</th><th>Requirement</th><th>Retention</th><th>Regulations</th><th>Source sensitivity</th><th>Traced to</th></tr></thead>
              <tbody>{a.data_requirements.map((d) => (
                <tr key={d.req_id}><td><code>{d.req_id}</code></td><td className="small">{d.statement}</td>
                  <td className="small">{d.retention.join("; ") || "—"}</td><td className="small">{d.regulations.join("; ") || "—"}</td>
                  <td>{d.source_sensitivity ? <span className={`tag sens-${d.source_sensitivity}`}>{d.source_sensitivity}</span> : "—"}</td>
                  <td><TraceCell t={d.trace} /></td></tr>
              ))}</tbody></table>
          )}
        </section>
      )}
      {view === "Interface requirements" && (
        <section className="card table-scroll">
          {a.interface_requirements.length === 0 ? <div className="empty">No integration requirements in the baseline.</div> : (
            <table><thead><tr><th>Req</th><th>Interface requirement</th><th>Depends on</th><th>Acceptance criteria</th><th>Traced to</th></tr></thead>
              <tbody>{a.interface_requirements.map((d) => (
                <tr key={d.req_id}><td><code>{d.req_id}</code></td><td className="small">{d.statement}</td>
                  <td className="small">{d.dependencies.join("; ") || "—"}</td>
                  <td className="small">{d.acceptance_criteria.join("; ") || "—"}</td><td><TraceCell t={d.trace} /></td></tr>
              ))}</tbody></table>
          )}
        </section>
      )}
      {view === "Threat & risk register" && (
        <section className="card table-scroll">
          <table><thead><tr><th>ID</th><th>Entry</th><th>Threat / risk</th><th>Level</th><th>Mitigation / control</th><th>Traced to</th></tr></thead>
            <tbody>{a.threat_risk_register.map((r) => (
              <tr key={r.id}><td><code>{r.id}</code></td><td>{r.entry}<div className="small muted">{r.type.replace(/_/g, " ")}</div></td>
                <td><strong>{r.title}</strong>{r.score !== undefined && <div className="small muted">L{r.likelihood}×I{r.impact} = {r.score}</div>}
                  {r.citation && <div className="small muted">{r.citation}</div>}</td>
                <td><span className={`tag sev-${r.level}`}>{r.level}</span></td>
                <td className="small">{r.mitigation}{r.entry === "threat" && <div>{r.control_requirement
                  ? <>control: <code>{r.control_requirement}</code></> : <span className="warn-text">control not accepted into the baseline</span>}</div>}</td>
                <td><TraceCell t={r.trace} /></td></tr>
            ))}</tbody></table>
        </section>
      )}
      {view === "Assumptions & dependencies" && (
        <section className="card table-scroll">
          {a.assumptions_dependencies.length === 0 ? <div className="empty">No assumptions or dependencies recorded.</div> : (
            <table><thead><tr><th>ID</th><th>Kind</th><th>Text</th><th>Requirement</th><th>Traced to</th></tr></thead>
              <tbody>{a.assumptions_dependencies.map((x) => (
                <tr key={x.id}><td><code>{x.id}</code></td>
                  <td>{x.kind}{x.kind === "dependency" && <div className="small muted">{x.on_requirement ? "on requirement" : "external"}</div>}</td>
                  <td className="small">{x.text}</td><td><code>{x.req_id}</code></td><td><TraceCell t={x.trace} /></td></tr>
              ))}</tbody></table>
          )}
        </section>
      )}
      {view === "User stories" && (
        <section className="card">
          {a.user_stories.map((s) => (
            <div key={s.req_id} className="story">
              <code>{s.req_id}</code> As a <strong>{s.as_a}</strong>, I want <strong>{s.i_want}</strong>, so that {s.so_that}.
              <ul className="small muted">{s.acceptance_criteria.map((c) => <li key={c}>{c}</li>)}</ul>
            </div>
          ))}
        </section>
      )}
      {view === "Traceability matrix" && (
        <section className="card table-scroll">
          <table>
            <thead><tr><th>Req</th><th>Status</th><th>Stakeholder / origin</th><th>Source (hash) and statement</th><th>Regulations</th><th>Grounded in</th><th>Risks</th><th>Use case</th><th>Story</th><th>SDLC phase</th><th>Tests</th><th>Approved by</th></tr></thead>
            <tbody>{a.traceability_matrix.map((r) => (
              <tr key={r.req_id}>
                <td><code>{r.req_id}</code><div className="small muted">{r.statement}</div></td>
                <td><span className={`tag st-${r.status}`}>{r.status}</span></td>
                <td className="small">{r.stakeholder_role ? catalog.role[r.stakeholder_role]?.name : r.origin.replace(/_/g, " ")}</td>
                <td className="small">{r.source_title}{r.source_sha256 && <div className="muted"><code>{r.source_sha256.slice(0, 12)}…</code></div>}
                  {r.source_quote && <div className="quote">“{r.source_quote}”</div>}</td>
                <td className="small">{r.regulations.join("; ") || "—"}</td>
                <td className="small">{r.citations?.join("; ") || <span className="muted">{r.grounding_support?.replace(/_/g, " ") ?? "—"}</span>}
                  {r.escalated && <div><span className="tag sev-medium">human-reviewed</span></div>}</td>
                <td className="small">{r.risks.join(", ") || "—"}</td>
                <td className="small">{r.use_cases.join(", ") || "—"}</td>
                <td>{r.user_story ? "Yes" : "—"}</td>
                <td className="small">{r.sdlc_phase ?? "—"}</td>
                <td>{r.tests}</td>
                <td className="small">{r.approved_by.join(", ")}</td>
              </tr>
            ))}</tbody>
          </table>
        </section>
      )}
      {view === "Compliance matrix" && (
        <section className="card stack">
          {a.compliance_matrix.determination && <p className="note">{a.compliance_matrix.determination} High-impact interpretations are approved by compliance &amp; legal.</p>}
          <div className="table-scroll">
          <table><thead><tr><th>Req</th><th>Jurisdiction · regulation</th><th>Obligation</th><th>Required controls</th><th>Evidence</th><th>Impact</th><th>Legal review</th></tr></thead>
            <tbody>{a.compliance_matrix.mappings.map((m, n) => (
              <tr key={n}><td><code>{m.req_id}</code></td><td>{m.jurisdiction && <span className="chip">{m.jurisdiction}</span>} {m.regulation}</td>
                <td className="small">{m.obligation}{m.obligation_type && m.obligation_type !== "other" && <div className="muted">{m.obligation_type.replace(/_/g, " ")}{m.retention_period && ` · ${m.retention_period}`}</div>}</td>
                <td className="small">{m.required_controls?.join("; ") || "—"}</td>
                <td className="small"><code>{m.evidence_ref}</code>{m.citation && <div className="muted">{m.citation}</div>}</td>
                <td>{m.impact && <span className={`tag sev-${m.impact}`}>{m.impact}</span>}</td>
                <td className="small">{m.legal_approval ? <>approved by {m.legal_approval.by}</> : m.needs_legal_review ? <span className="warn-text">required</span> : "—"}</td></tr>
            ))}</tbody></table>
          </div>
          <h3>Mandatory approval and audit checkpoints</h3>
          {(a.compliance_matrix.checkpoints ?? []).length === 0 ? <p className="muted small">None identified.</p> : (
            <ul>{a.compliance_matrix.checkpoints!.map((c, n) => (
              <li key={n}><strong>{c.name}</strong> <span className="small muted">· {c.stage} · {catalog.role[c.approver_role]?.name ?? c.approver_role} · {c.regulation}</span></li>
            ))}</ul>
          )}
          <h3>Data-retention and reporting obligations</h3>
          {(a.compliance_matrix.retention_and_reporting ?? []).length === 0 ? <p className="muted small">None identified.</p> : (
            <ul>{a.compliance_matrix.retention_and_reporting!.map((o, n) => (
              <li key={n}><span className="tag">{o.kind.replace(/_/g, " ")}</span> {o.obligation}{o.period && <strong> · {o.period}</strong>}
                <span className="small muted"> · {o.regulation} ({o.jurisdiction}) · <code>{o.req_id}</code></span></li>
            ))}</ul>
          )}
          <h3>Gaps</h3>
          <ul>{a.compliance_matrix.gaps.map((g, n) => (
            <li key={n}><strong>{g.regulation}</strong>: {g.description} → {g.addressed_by ? <code>{g.addressed_by}</code> : <span className="warn-text">open</span>}</li>
          ))}</ul>
        </section>
      )}
      {view === "Open issues" && (
        <section className="card table-scroll">
          <table><thead><tr><th>Issue</th><th>Traced to</th></tr></thead>
            <tbody>{a.open_issues.map((i, n) => (
              <tr key={n}><td className="small">{"question" in i ? <>{i.question} <span className="muted">(→ {catalog.role[i.target_role]?.name ?? i.target_role})</span></> : <><span className="tag">{i.type.replace(/_/g, " ")}</span> {i.message}</>}</td>
                <td><TraceCell t={i.trace} /></td></tr>
            ))}</tbody></table>
        </section>
      )}
    </div>
  );
}
