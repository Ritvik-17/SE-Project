import { useState } from "react";
import type { BaselineGate, Decision, DecisionItem, Requirement } from "../../api";
import { useCatalog } from "../../catalog";
import ApproverBar from "./ApproverBar";

interface Props { gate: BaselineGate; busy: boolean; onDecide: (label: string, d: Decision) => void }
type Edit = { action: "accept" | "reject" | "modify"; statement?: string };
type Legal = { action: "accept" | "reject" | "modify"; regulation?: string; obligation?: string; note?: string };

const VIEWS = ["Requirements", "Issues", "Conflicts", "Compliance", "Security & privacy", "Risks", "Clarifications"] as const;

export default function BaselineGateView({ gate, busy, onDecide }: Props) {
  const [view, setView] = useState<(typeof VIEWS)[number]>("Requirements");
  const [edits, setEdits] = useState<Record<string, Edit>>({});
  const q = gate.quality;
  const counts: Record<string, number> = {
    Requirements: gate.requirements.length, Issues: gate.issues.length, Conflicts: gate.conflicts.length,
    Compliance: gate.compliance.mappings.length + gate.compliance.gaps.length,
    "Security & privacy": gate.security_findings.length, Risks: gate.risks.length, Clarifications: gate.clarifications.length,
  };

  const editList = Object.entries(edits).map(([id, e]) => ({ id, ...e }));
  const catalog = useCatalog();
  const items = gate.decision_items ?? {};
  const [legal, setLegal] = useState<Record<string, Legal>>({});
  const openItems = Object.entries(items).filter(([id, it]) => !it.decided && !edits[id]);
  const openLegal = (gate.interpretations ?? []).filter((m) => !m.legal_decision && !legal[m.id!]);
  const byOwner = new Map<string, string[]>();
  openItems.forEach(([id, it]) => byOwner.set(it.owner, [...(byOwner.get(it.owner) ?? []), id]));
  const blockerFor = (role: string) => {
    const mine = byOwner.get(role) ?? [];
    if (mine.length) return `Decide your ${mine.length} requirement(s) first: ${mine.join(", ")}`;
    if (role === "compliance_legal" && openLegal.length) return `Decide the regulatory interpretations first: ${openLegal.map((m) => m.id).join(", ")}`;
    return undefined;
  };
  const decide = (decision: "approve" | "regenerate") => (reviewer: string, role: string, feedback: string) => {
    const interpretations = decision === "approve" && role === "compliance_legal"
      ? Object.entries(legal).map(([id, d]) => ({ id, ...d })) : [];
    onDecide(decision === "approve" ? "Recording approval…" : "Regenerating with feedback…",
      { gate: "baseline", decision, reviewer, reviewer_role: role, feedback, edits: decision === "approve" ? editList : [], interpretations });
    setEdits({});
    setLegal({});
  };

  return (
    <div className="stack">
      <div className="section-head">
        <h2>Requirement baseline: approval</h2>
        <span className="muted small num">{gate.requirements.filter((r) => r.status !== "suggested").length} extracted ·{" "}
          {gate.requirements.filter((r) => r.status === "suggested").length} suggested by agents</span>
      </div>
      <div className="metrics">
        {(["overall", "completeness", "consistency", "evidence", "testability", "grounding"] as const).filter((k) => q[k] !== undefined).map((k) => (
          <div key={k} className={`metric ${k === "overall" ? "main" : ""}`}>
            <span className="eyebrow">{k}</span>
            <span className="metric-value">{Math.round((q[k] ?? 0) * 100)}<span className="small muted">%</span></span>
            <span className="meter"><span style={{ width: `${(q[k] ?? 0) * 100}%` }} /></span>
          </div>
        ))}
      </div>

      <div className="tabs sub">
        {VIEWS.map((v) => (
          <button key={v} className={view === v ? "active" : ""} onClick={() => setView(v)}>
            {v}<span className="count">{counts[v]}</span>
          </button>
        ))}
      </div>

      {view === "Requirements" && <RequirementsReview requirements={gate.requirements} edits={edits} setEdits={setEdits} items={items} />}
      {view === "Issues" && (
        <section className="card stack">
          {q.checks && (
            <div>
              <h3>Quality checks <span className="small muted">· requirements failing each check</span></h3>
              <div className="check-grid">
                {Object.entries(CHECK_LABEL).map(([id, label]) => (
                  <div key={id} className={`check ${q.checks![id] ? "fail" : "pass"}`}>
                    <span aria-hidden>{q.checks![id] ? "✗" : "✓"}</span> {label} <span className="num muted">{q.checks![id] ?? 0}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {(gate.returned?.length ?? 0) > 0 && (
            <p className="note">
              {gate.returned!.length} requirement{gate.returned!.length > 1 ? "s" : ""} failed a check and {gate.returned!.length > 1 ? "were" : "was"} returned
              to the clarification agent ({gate.returned!.filter((r) => r.blocking).length} blocking). Their questions are in the Clarifications tab.
            </p>
          )}
          <ul className="issues">
            {[...gate.issues].sort((a, b) => sevRank(a.severity) - sevRank(b.severity)).map((i, n) => (
              <li key={n} className={`stripe ${i.severity}`}><span className={`tag sev-${i.severity}`}>{i.severity}</span> <span className="tag">{i.type.replace(/_/g, " ")}</span>{" "}
                {i.check && <span className="tag accent">{CHECK_LABEL[i.check] ?? i.check}</span>}{" "}
                <strong>{i.req_id ?? "Overall"}</strong>: {i.message}</li>
            ))}
          </ul>
        </section>
      )}
      {view === "Conflicts" && (
        <section className="card">
          {gate.conflicts.length === 0 ? <p className="muted">No conflicts detected.</p> : (
            <table><thead><tr><th>Kind</th><th>Requirements</th><th>Description</th><th>Suggested resolution</th></tr></thead>
              <tbody>{gate.conflicts.map((c, n) => (
                <tr key={n}><td><span className="tag">{c.kind}</span></td><td>{c.req_ids.join(", ")}</td><td>{c.description}</td><td>{c.suggested_resolution}</td></tr>
              ))}</tbody></table>
          )}
        </section>
      )}
      {view === "Compliance" && (
        <section className="card stack">
          <p className="muted small">
            Evidence passages retrieved: {gate.compliance.evidence.length || "none (knowledge base empty)"}. The compliance agent does not
            make legal determinations. Mappings without knowledge-base evidence are flagged for legal review.
          </p>
          {(gate.interpretations?.length ?? 0) > 0 && (
            <Interpretations items={gate.interpretations!} legal={legal} setLegal={setLegal} />
          )}
          <table><thead><tr><th>Req</th><th>Regulation</th><th>Obligation</th><th>Evidence</th><th>Conf.</th><th>Review</th></tr></thead>
            <tbody>{gate.compliance.mappings.map((m, n) => (
              <tr key={n}><td><code>{m.req_id}</code></td><td>{m.regulation}</td><td>{m.obligation}</td>
                <td className="small">{m.evidence ? <>“{m.evidence}” <code>{m.evidence_ref}</code></> : <code>{m.evidence_ref}</code>}</td>
                <td>{m.confidence.toFixed(2)}</td><td>{m.needs_legal_review ? <span className="tag sev-medium">legal review</span> : "—"}</td></tr>
            ))}</tbody></table>
          {gate.compliance.gaps.length > 0 && <>
            <h3>Gaps</h3>
            <ul>{gate.compliance.gaps.map((g, n) => <li key={n}><strong>{g.regulation}</strong>: {g.description}</li>)}</ul>
          </>}
        </section>
      )}
      {view === "Security & privacy" && (
        <section className="card">
          <table><thead><tr><th>Severity</th><th>Kind</th><th>Finding</th><th>Suggested requirement</th></tr></thead>
            <tbody>{gate.security_findings.map((f, n) => (
              <tr key={n}><td><span className={`tag sev-${f.severity}`}>{f.severity}</span></td><td>{f.kind.replace(/_/g, " ")}{f.req_id && <div><code>{f.req_id}</code></div>}</td>
                <td>{f.description}</td><td className="small">{f.suggested_requirement}</td></tr>
            ))}</tbody></table>
        </section>
      )}
      {view === "Risks" && <RiskTable risks={gate.risks} />}
      {view === "Clarifications" && (
        <section className="card">
          <ul>{gate.clarifications.map((c, n) => <li key={n}><span className="tag">{c.severity}</span> {c.question} <span className="muted small">→ {c.target_role}</span></li>)}</ul>
        </section>
      )}

      {(openItems.length > 0 || openLegal.length > 0) && (
        <div className="alert warn">
          <strong>Human decisions required before approval</strong> (accept, modify or reject; each is owned by one role):
          <ul className="small" style={{ margin: "0.3rem 0 0", paddingLeft: "1.1rem" }}>
            {[...byOwner].map(([owner, ids]) => <li key={owner}>{catalog.role[owner]?.name ?? owner}: {ids.join(", ")}</li>)}
            {openLegal.length > 0 && <li>Compliance and legal officers, regulatory interpretations: {openLegal.map((m) => m.id).join(", ")} (Compliance tab)</li>}
          </ul>
        </div>
      )}
      {editList.length > 0 && <div className="alert info">{editList.length} pending edit(s) will be applied with your approval.</div>}
      <ApproverBar required={gate.required_approvers} pending={gate.pending_approvers} approvals={gate.approvals} busy={busy}
        blockerFor={blockerFor}
        approveLabel="Approve baseline" onApprove={decide("approve")} onRegenerate={decide("regenerate")} />
    </div>
  );
}

// Step 10 quality checks (app/agents/standards.py QUALITY_CHECKS)
const CHECK_LABEL: Record<string, string> = {
  ambiguity: "Ambiguity", incompleteness: "Incompleteness", inconsistency: "Inconsistency", duplication: "Duplication",
  infeasibility: "Infeasibility", lack_of_testability: "Testability", missing_source: "Missing source",
  undefined_terminology: "Undefined terms", conflicting_stakeholder_expectations: "Stakeholder conflict",
  missing_controls: "Missing controls",
};

function sevRank(s: string) { return s === "high" ? 0 : s === "medium" ? 1 : 2; }

function RequirementsReview({ requirements, edits, setEdits, items }: {
  requirements: Requirement[]; edits: Record<string, Edit>; setEdits: (e: Record<string, Edit>) => void;
  items: Record<string, DecisionItem>;
}) {
  const catalog = useCatalog();
  const set = (id: string, e: Edit | null) => {
    const next = { ...edits };
    if (e) next[id] = e; else delete next[id];
    setEdits(next);
  };
  return (
    <section className="card">
      <p className="note">
        Suggested requirements (<code>SUG-…</code>) come from the security and compliance agents. They join the baseline only if accepted.
      </p>
      <div className="table-scroll">
        <table>
          <thead><tr><th>ID</th><th>Requirement</th><th>Grounding</th><th>Prio</th><th>Confidence</th><th>Source</th><th>Status</th><th>Action</th></tr></thead>
          <tbody>
            {requirements.map((r) => {
              const e = edits[r.id];
              const effective = e ? (e.action === "accept" ? "accepted" : e.action === "reject" ? "rejected" : "modified") : r.status;
              return (
                <tr key={r.id} className={`req-${effective} ${items[r.id] && !items[r.id].decided && !e ? "req-escalated" : ""}`}>
                  <td className="nowrap"><code>{r.id}</code></td>
                  <td>
                    {e?.action === "modify" ? (
                      <textarea rows={2} value={e.statement ?? r.statement} onChange={(ev) => set(r.id, { action: "modify", statement: ev.target.value })} />
                    ) : r.statement}
                    {r.original_statement && <div className="muted small">was: {r.original_statement}</div>}
                    {r.rationale && <div className="muted small">{r.rationale}</div>}
                    {r.source_quote && <div className="quote small">“{r.source_quote}”</div>}
                    {items[r.id] && (
                      <div className="small">
                        <span className={`tag ${items[r.id].decided ? "ok" : "sev-medium"}`}>
                          {items[r.id].decided ? "decided" : "decision"} by {catalog.role[items[r.id].owner]?.name ?? items[r.id].owner}
                        </span> <span className="muted">{items[r.id].reasons.join("; ")}</span>
                      </div>
                    )}
                    {r.escalated && !items[r.id] && <div className="small warn-text">Escalated: {r.escalation_reasons?.join("; ")}</div>}
                    <div>{r.categories.map((c) => <span key={c} className="chip">{c}</span>)}
                      {r.risk_level && <span className={`tag sev-${r.risk_level}`}>risk {r.risk_level}</span>}</div>
                    <RecordFields r={r} />
                  </td>
                  <td className="small"><GroundingCell r={r} /></td>
                  <td><span className={`tag prio-${r.priority}`}>{r.priority}</span></td>
                  <td className="num">
                    <span className={r.confidence < 0.6 ? "warn-text" : ""}>{r.confidence.toFixed(2)}</span>
                    {r.extraction_confidence !== undefined && <div className="small muted">extracted {r.extraction_confidence.toFixed(2)}</div>}
                  </td>
                  <td className="small">{r.source_title}<div className="muted">{r.stakeholder_role ? catalog.role[r.stakeholder_role]?.name : r.origin.replace(/_/g, " ")}</div></td>
                  <td><span className={`tag st-${effective}`}>{effective}</span></td>
                  <td className="nowrap">
                    <select value={e?.action ?? ""} onChange={(ev) => {
                      const a = ev.target.value as Edit["action"] | "";
                      set(r.id, a ? { action: a, statement: a === "modify" ? r.statement : undefined } : null);
                    }}>
                      <option value="">—</option>
                      <option value="accept">Accept</option>
                      <option value="reject">Reject</option>
                      <option value="modify">Modify</option>
                    </select>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/** Step-8 fields that are not already columns. */
function RecordFields({ r }: { r: Requirement }) {
  const deps = [...(r.depends_on ?? []), ...(r.dependencies ?? [])];
  const rows: [string, string][] = [
    ["Justification", r.business_justification || ""], ["Depends on", deps.join("; ")],
    ["Assumes", (r.assumptions ?? []).join("; ")], ["Regulations", (r.applicable_regulations ?? []).join("; ")],
  ];
  const shown = rows.filter(([, v]) => v);
  if (!shown.length) return r.origin === "extracted" ? <div className="small muted">No justification given</div> : null;
  return <dl className="record small">{shown.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>;
}

const SUPPORT_LABEL: Record<string, [string, string]> = {
  supported: ["supported", "ok"], partially_supported: ["partly supported", "accent"], unsupported: ["unsupported", "sev-medium"],
  contradicts_evidence: ["contradicts policy", "sev-high"], no_obligation_expected: ["no source needed", ""],
};

function GroundingCell({ r }: { r: Requirement }) {
  if (!r.grounding_support) return <span className="muted">—</span>;
  const [label, cls] = SUPPORT_LABEL[r.grounding_support];
  return (
    <>
      <span className={`tag ${cls}`}>{label}</span>
      {r.citations?.map((c) => <div key={c.ref} title={c.ref}><code>{c.ref}</code> {c.citation} <span className="muted">({c.strength})</span></div>)}
      {r.grounding_note && r.grounding_support !== "no_obligation_expected" && <div className="muted">{r.grounding_note}</div>}
    </>
  );
}

/** Regulatory interpretations: compliance and legal officers accept, reject or correct each one (step 16). */
function Interpretations({ items, legal, setLegal }: {
  items: NonNullable<BaselineGate["interpretations"]>; legal: Record<string, Legal>; setLegal: (l: Record<string, Legal>) => void;
}) {
  const set = (id: string, d: Legal | null) => {
    const next = { ...legal };
    if (d) next[id] = d; else delete next[id];
    setLegal(next);
  };
  return (
    <div className="stack">
      <h3>Regulatory interpretations for legal decision</h3>
      <p className="note">The compliance agent proposes; it does not make legal determinations. Compliance and legal officers decide
        each interpretation below (sent with their approval).</p>
      {items.map((m) => {
        const d = legal[m.id!];
        return (
          <div key={m.id} className="card stack interp">
            <div className="section-head">
              <strong><code>{m.id}</code> {m.regulation}</strong>
              <span className="small muted">{m.req_id} · impact {m.impact ?? "—"} · evidence {m.evidence_strength ?? "none"}</span>
            </div>
            <p className="small">{m.obligation}{m.evidence && <span className="muted"> · “{m.evidence}” <code>{m.evidence_ref}</code></span>}</p>
            {m.legal_decision ? (
              <p className="small"><span className="tag ok">{m.legal_decision.action}</span> by {m.legal_decision.by} {m.legal_decision.note && `· ${m.legal_decision.note}`}</p>
            ) : (
              <div className="row">
                <label className="grow">Decision
                  <select value={d?.action ?? ""} onChange={(e) => set(m.id!, e.target.value ? { action: e.target.value as Legal["action"] } : null)}>
                    <option value="">—</option><option value="accept">Accept</option><option value="reject">Reject</option><option value="modify">Modify</option>
                  </select>
                </label>
                {d?.action === "modify" && <>
                  <label className="grow">Regulation<input value={d.regulation ?? m.regulation} onChange={(e) => set(m.id!, { ...d, regulation: e.target.value })} /></label>
                  <label className="grow">Obligation<input value={d.obligation ?? m.obligation} onChange={(e) => set(m.id!, { ...d, obligation: e.target.value })} /></label>
                </>}
                {d && <label className="grow">Note<input value={d.note ?? ""} onChange={(e) => set(m.id!, { ...d, note: e.target.value })} /></label>}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function RiskTable({ risks }: { risks: BaselineGate["risks"] }) {
  return (
    <section className="card">
      <table><thead><tr><th>ID</th><th>Risk</th><th>Type</th><th>L×I</th><th>Level</th><th>Mitigation</th><th>Reqs</th></tr></thead>
        <tbody>{risks.map((r) => (
          <tr key={r.id}><td><code>{r.id}</code></td><td><strong>{r.title}</strong><div className="muted small">{r.description}</div></td>
            <td>{r.type}</td><td>{r.likelihood}×{r.impact}={r.score}</td><td><span className={`tag sev-${r.level}`}>{r.level}</span></td>
            <td className="small">{r.mitigation}</td><td className="small">{r.related_req_ids.join(", ")}</td></tr>
        ))}</tbody></table>
    </section>
  );
}
