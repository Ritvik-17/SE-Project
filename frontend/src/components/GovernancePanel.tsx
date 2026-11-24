import { useCallback, useEffect, useState } from "react";
import { useMe } from "../auth";
import { api, type ApprovalRequest, type HitlControl, type Project } from "../api";
import { useCatalog } from "../catalog";

interface Props { project: Project; onProjectChanged: () => void }

const STATUS_CLASS: Record<string, string> = {
  approved: "ok", decided: "ok", applied: "ok", "not applicable": "", "not reached": "", "not requested": "",
  pending: "sev-medium", changes_requested: "sev-medium", rejected: "sev-high", approved_with_conditions: "accent",
};

/** Step 16 after the analysis: the human-in-the-loop register, change requests and production-readiness reviews. */
export default function GovernancePanel({ project, onProjectChanged }: Props) {
  const catalog = useCatalog();
  const { me } = useMe();
  const who = me.username;  // actions are recorded under the signed-in account
  const [role, setRole] = useState("project_manager");
  const [register, setRegister] = useState<HitlControl[]>([]);
  const [changes, setChanges] = useState<ApprovalRequest[]>([]);
  const [reviews, setReviews] = useState<ApprovalRequest[]>([]);
  const [reqs, setReqs] = useState<{ req_id: string; statement: string; approval_status: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => Promise.all([
    api.hitl(project.id).then(setRegister), api.changeRequests(project.id).then(setChanges),
    api.readinessReviews(project.id).then(setReviews), api.requirements(project.id).then(setReqs),
  ]).catch((e: Error) => setError(e.message)), [project.id]);
  useEffect(() => { load(); }, [load]);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true); setError(null);
    try { await fn(); await load(); onProjectChanged(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const roleName = (r: string) => catalog.role[r]?.name ?? r;
  const ready = ["completed", "artifacts_stale"].includes(project.status);

  return (
    <div className="stack">
      <section className="card">
        <h2>Human-in-the-loop controls</h2>
        <p className="muted small">Every decision the system cannot take on its own, where it is taken, by whom, and its status for this project.</p>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Control</th><th>Where</th><th>Who decides</th><th>Status</th><th>Evidence</th></tr></thead>
            <tbody>{register.map((c) => (
              <tr key={c.id}>
                <td><strong>{c.name}</strong><div className="small muted">{c.actions}</div></td>
                <td className="small">{c.where}</td><td className="small">{c.who}</td>
                <td><span className={`tag ${STATUS_CLASS[c.status] ?? (c.status.endsWith(" open") && !c.status.startsWith("0") ? "sev-medium" : "")}`}>{c.status}</span>
                  {c.open && c.open.length > 0 && <div className="small warn-text">open: {c.open.join(", ")}</div>}</td>
                <td className="small">{c.evidence.length ? <ul>{c.evidence.slice(0, 4).map((e) => <li key={e}>{e}</li>)}</ul> : "—"}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </section>

      {!ready ? <div className="empty">Change requests and production-readiness reviews open once the analysis has completed.</div> : <>
        <section className="card row acting-as">
          <div className="grow small muted">Signed in as <strong>{me.display_name}</strong></div>
          <label className="grow">Acting as<select value={role} onChange={(e) => setRole(e.target.value)}>
            {catalog.roles.filter((r) => me.roles.includes(r.id)).map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
        </section>
        {error && <div className="alert error">{error}</div>}

        {project.status === "artifacts_stale" && (
          <div className="alert warn row between">
            <span>An approved change altered the baseline; the documents are out of date.</span>
            <button className="primary" disabled={busy || !who.trim()}
              onClick={() => act(() => api.regenerateArtifacts(project.id, { requested_by: who.trim(), role }))}>Regenerate documents</button>
          </div>
        )}

        <ChangeRequests changes={changes} reqs={reqs} who={who} role={role} busy={busy} roleName={roleName}
          onPropose={(b) => act(() => api.proposeChange(project.id, { ...b, requested_by: who.trim(), role }))}
          onDecide={(id, decision, comment) => act(() => api.decideChange(project.id, id, { reviewer: who.trim(), reviewer_role: role, decision, comment }))}
          onRevise={(id, statement) => act(() => api.reviseChange(project.id, id, { requested_by: who.trim(), statement, reason: "" }))} />

        <Readiness reviews={reviews} who={who} role={role} busy={busy} roleName={roleName}
          onOpen={(release) => act(() => api.openReadiness(project.id, { requested_by: who.trim(), role, release }))}
          onDecide={(id, body) => act(() => api.decideReadiness(project.id, id, { reviewer: who.trim(), reviewer_role: role, ...body }))} />
      </>}
    </div>
  );
}

function ChangeRequests({ changes, reqs, who, role, busy, roleName, onPropose, onDecide, onRevise }: {
  changes: ApprovalRequest[]; reqs: { req_id: string; statement: string; approval_status: string }[]; who: string; role: string;
  busy: boolean; roleName: (r: string) => string;
  onPropose: (b: { action: string; req_id?: string; statement?: string; reason: string; categories?: string[] }) => void;
  onDecide: (id: number, decision: string, comment: string) => void; onRevise: (id: number, statement: string) => void;
}) {
  const catalog = useCatalog();
  const [action, setAction] = useState("modify");
  const [reqId, setReqId] = useState("");
  const [statement, setStatement] = useState("");
  const [reason, setReason] = useState("");
  const [category, setCategory] = useState("functional");
  const [comments, setComments] = useState<Record<number, string>>({});
  const active = reqs.filter((r) => !["rejected", "removed", "suggested"].includes(r.approval_status));

  return (
    <section className="card stack">
      <h2>Changes to approved requirements</h2>
      <p className="muted small">The approved baseline changes only through a change request. Its impact decides who must approve;
        approved changes create a new requirement version and mark the documents out of date.</p>
      <div className="row">
        <label>Change<select value={action} onChange={(e) => setAction(e.target.value)}>
          <option value="modify">Modify</option><option value="add">Add</option><option value="remove">Remove</option></select></label>
        {action !== "add" ? (
          <label className="grow">Requirement<select value={reqId} onChange={(e) => {
            setReqId(e.target.value); setStatement(active.find((r) => r.req_id === e.target.value)?.statement ?? "");
          }}><option value="">—</option>{active.map((r) => <option key={r.req_id} value={r.req_id}>{r.req_id}</option>)}</select></label>
        ) : (
          <label className="grow">Category<select value={category} onChange={(e) => setCategory(e.target.value)}>
            {catalog.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        )}
      </div>
      {action !== "remove" && <label>New statement<textarea rows={2} value={statement} onChange={(e) => setStatement(e.target.value)} /></label>}
      <label>Reason<input value={reason} onChange={(e) => setReason(e.target.value)} /></label>
      <div><button className="primary" disabled={busy || !who.trim() || !reason.trim() || (action !== "add" && !reqId) || (action !== "remove" && !statement.trim())}
        onClick={() => { onPropose({ action, req_id: action === "add" ? undefined : reqId, statement: action === "remove" ? undefined : statement, reason,
          categories: action === "add" ? [category] : [] }); setReason(""); }}>Propose change</button></div>

      {changes.slice().reverse().map((c) => {
        const imp = c.payload.impact!;
        return (
          <article key={c.id} className={`card stack stripe ${c.status === "pending" ? "medium" : c.status === "rejected" ? "high" : "low"}`}>
            <div className="section-head">
              <h3>CR-{c.id} {c.title}</h3>
              <span className={`tag ${STATUS_CLASS[c.status] ?? ""}`}>{c.status.replace(/_/g, " ")}</span>
            </div>
            {c.payload.current_statement && <p className="small muted">Was: {c.payload.current_statement}</p>}
            {c.payload.statement && <p className="small">Proposed: {c.payload.statement}</p>}
            <p className="small">Reason: {c.payload.reason} · by {c.created_by} ({roleName(c.created_role)})</p>
            <p className="small"><span className={`tag sev-${imp.level}`}>impact {imp.level}</span>{" "}
              {[imp.dependent_requirements.length && `dependents: ${imp.dependent_requirements.join(", ")}`,
                imp.use_cases.length && `use cases: ${imp.use_cases.join(", ")}`, imp.regulations.length && `regulations: ${imp.regulations.join("; ")}`,
                imp.risks.length && `risks: ${imp.risks.join(", ")}`, imp.workflow_phases.length && `phases: ${imp.workflow_phases.join(", ")}`]
                .filter(Boolean).join(" · ")}
              <span className="muted"> · regenerates {imp.artefacts_to_regenerate.length} documents</span></p>
            <p className="small">Approvers: {c.required_roles.map((r) => `${roleName(r)}${c.pending_roles.includes(r) ? "" : " ✓"}`).join(", ")}</p>
            {c.decisions.filter((d) => d.comment).map((d, i) => <p key={i} className="small muted">{d.reviewer} ({d.role && roleName(d.role)}): {d.decision.replace(/_/g, " ")}, “{d.comment}”</p>)}
            {c.status === "pending" && c.pending_roles.includes(role) && (
              <div className="row">
                <input className="grow" placeholder="Comment (required to reject or request changes)" value={comments[c.id] ?? ""}
                  onChange={(e) => setComments({ ...comments, [c.id]: e.target.value })} />
                <button className="primary" disabled={busy || !who.trim()} onClick={() => onDecide(c.id, "approve", comments[c.id] ?? "")}>Approve</button>
                <button disabled={busy || !who.trim() || !(comments[c.id] ?? "").trim()} onClick={() => onDecide(c.id, "request_changes", comments[c.id] ?? "")}>Request changes</button>
                <button className="link danger" disabled={busy || !who.trim() || !(comments[c.id] ?? "").trim()} onClick={() => onDecide(c.id, "reject", comments[c.id] ?? "")}>Reject</button>
              </div>
            )}
            {c.status === "changes_requested" && (
              <div className="row">
                <input className="grow" placeholder="Revised statement" value={comments[-c.id] ?? c.payload.statement ?? ""}
                  onChange={(e) => setComments({ ...comments, [-c.id]: e.target.value })} />
                <button disabled={busy || !who.trim()} onClick={() => onRevise(c.id, comments[-c.id] ?? c.payload.statement ?? "")}>Resubmit</button>
              </div>
            )}
          </article>
        );
      })}
    </section>
  );
}

function Readiness({ reviews, who, role, busy, roleName, onOpen, onDecide }: {
  reviews: ApprovalRequest[]; who: string; role: string; busy: boolean; roleName: (r: string) => string;
  onOpen: (release: string) => void;
  onDecide: (id: number, body: { decision: string; comment: string; attest: string[]; waivers: Record<string, string> }) => void;
}) {
  const [release, setRelease] = useState("Release 1");
  const [attest, setAttest] = useState<Record<string, boolean>>({});
  const [waive, setWaive] = useState<Record<string, string>>({});
  const [comment, setComment] = useState("");

  function decide(id: number, decision: string) {
    onDecide(id, { decision, comment, attest: Object.keys(attest).filter((k) => attest[k]),
      waivers: Object.fromEntries(Object.entries(waive).filter(([, v]) => v.trim())) });
    setAttest({}); setWaive({}); setComment("");
  }

  return (
    <section className="card stack">
      <h2>Production readiness</h2>
      <p className="muted small">Go / no-go before a release reaches production. Each approver resolves, attests or waives (with a
        justification) the checklist items they own before saying go.</p>
      <div className="row">
        <label className="grow">Release<input value={release} onChange={(e) => setRelease(e.target.value)} /></label>
        <button disabled={busy || !who.trim() || !release.trim()} onClick={() => onOpen(release)}>Open readiness review</button>
      </div>
      {reviews.slice().reverse().map((r) => (
        <article key={r.id} className="card stack">
          <div className="section-head">
            <h3>{r.title}</h3>
            <span className={`tag ${STATUS_CLASS[r.status] ?? ""}`}>{r.status.replace(/_/g, " ")}</span>
          </div>
          <div className="table-scroll">
            <table>
              <thead><tr><th>Check</th><th>Owner</th><th>Status</th><th>Evidence / action</th></tr></thead>
              <tbody>{(r.payload.checklist ?? []).map((i) => {
                const mine = r.status === "pending" && i.owner === role && r.pending_roles.includes(role);
                return (
                  <tr key={i.id}>
                    <td className="small">{i.label}<div className="muted">{i.kind}</div></td>
                    <td className="small">{roleName(i.owner)}</td>
                    <td><span className={`tag ${i.status === "pass" ? "ok" : i.status === "waived" ? "accent" : i.status === "fail" ? "sev-high" : "sev-medium"}`}>{i.status}</span></td>
                    <td className="small">
                      {i.evidence}{i.attested_by && ` attested by ${i.attested_by}`}{i.waiver && ` waived by ${i.waiver.by}: ${i.waiver.justification}`}
                      {mine && i.kind === "attestation" && i.status === "pending" && (
                        <label className="row"><input type="checkbox" checked={!!attest[i.id]} onChange={(e) => setAttest({ ...attest, [i.id]: e.target.checked })} /> I attest this</label>
                      )}
                      {mine && i.status === "fail" && (
                        <input placeholder="Waiver justification" value={waive[i.id] ?? ""} onChange={(e) => setWaive({ ...waive, [i.id]: e.target.value })} />
                      )}
                    </td>
                  </tr>
                );
              })}</tbody>
            </table>
          </div>
          <p className="small">Decisions: {r.required_roles.map((x) => {
            const d = [...r.decisions].reverse().find((y) => y.role === x);
            return `${roleName(x)}: ${d ? d.decision.replace(/_/g, " ") : "pending"}`;
          }).join(" · ")}</p>
          {r.decisions.filter((d) => d.comment).map((d, i) => <p key={i} className="small muted">{d.reviewer}: “{d.comment}”</p>)}
          {r.status === "pending" && r.pending_roles.includes(role) && (
            <div className="row">
              <input className="grow" placeholder="Conditions (conditional go) or reasons (no-go)" value={comment} onChange={(e) => setComment(e.target.value)} />
              <button className="primary" disabled={busy || !who.trim()} onClick={() => decide(r.id, "go")}>Go</button>
              <button disabled={busy || !who.trim() || !comment.trim()} onClick={() => decide(r.id, "conditional")}>Conditional go</button>
              <button className="link danger" disabled={busy || !who.trim() || !comment.trim()} onClick={() => decide(r.id, "no_go")}>No-go</button>
            </div>
          )}
        </article>
      ))}
    </section>
  );
}
