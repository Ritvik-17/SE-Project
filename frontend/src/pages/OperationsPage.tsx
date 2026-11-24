import { useCallback, useEffect, useState } from "react";
import { api, type Deployment, type DomainReadiness, type QualityMonitor, type Usage } from "../api";
import { useMe } from "../auth";

const pct = (x: number | null) => (x === null ? "—" : `${Math.round(x * 100)}%`);
const LABELS: Record<string, string> = {
  requirement_modify: "Requirements modified by reviewers", requirement_reject: "Requirements rejected by reviewers",
  interpretation_modify: "Legal interpretations modified", interpretation_reject: "Legal interpretations rejected",
  sdlc_override: "SDLC recommendations overridden", workflow_modified: "Workflows edited before approval",
  compliance_gaps_found_by_agent: "Compliance gaps found by the agent", escalated_requirements: "Requirements escalated to humans",
  readiness_no_go: "Production readiness: no-go", injection_neutralised: "Prompt-injection attempts neutralised",
  llm_filtered: "Model outputs filtered", agent_permission_denied: "Agent permission denials",
  baseline_regenerate: "Baselines sent back for regeneration", sdlc_regenerate: "SDLC recommendations regenerated",
};

/** Step 20: staged deployment, re-evaluation status, quality monitoring, domain expansion and cost. */
export default function OperationsPage() {
  const { me } = useMe();
  const isAdmin = me.roles.includes("admin");
  const [dep, setDep] = useState<Deployment | null>(null);
  const [quality, setQuality] = useState<QualityMonitor | null>(null);
  const [domains, setDomains] = useState<DomainReadiness[]>([]);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [reason, setReason] = useState("");
  const [justify, setJustify] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(() => Promise.all([
    api.deployment().then(setDep), api.quality().then(setQuality), api.domains().then(setDomains), api.systemUsage().then(setUsage),
  ]).catch((e: Error) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  async function act(fn: () => Promise<unknown>, done: string) {
    setError(null); setNote(null);
    try { await fn(); await load(); setNote(done); } catch (e) { setError((e as Error).message); }
  }

  const ev = dep?.evaluation;
  return (
    <main className="page stack">
      <header className="page-head">
        <span className="eyebrow">Step 20 · deploy, monitor, improve</span>
        <h1>Deployment and monitoring</h1>
        <p className="muted">The assistant starts in advisory mode beside the business analysts, moves to assisted use only after a passing
          evaluation, and must be re-evaluated after every significant change. Regulatory interpretation, requirement approval and
          SDLC adoption always stay with authorised people.</p>
      </header>
      {error && <div className="alert error">{error}</div>}
      {note && <div className="alert ok">{note}</div>}

      {dep && ev && (
        <section className="card stack">
          <div className="section-head"><h2>Deployment stage</h2>
            <span className={`tag ${dep.stage === "advisory" ? "sev-medium" : "ok"}`}>{dep.stage}</span></div>
          <p className="small muted">
            <strong>Advisory:</strong> outputs are watermarked, kept out of the knowledge base, and compared with the analysts' own work.{" "}
            <strong>Assisted:</strong> documents generated after the human approval gates become the project's official artefacts.
            New projects start in the stage shown here{dep.require_current_evaluation ? ", and only in assisted when the current configuration has passed evaluation" : ""}.
          </p>
          {ev.current_evaluation_passed
            ? <div className="alert ok">Current configuration passed evaluation (run #{ev.passing_run?.id}, {ev.passing_run?.case}).</div>
            : <div className="alert warn">Re-evaluation required: no passing evaluation for the current model, prompts, rules and approved knowledge.
                {ev.changes_since_last_run.length > 0 && <> Changed since run #{ev.last_run?.id}: <code>{ev.changes_since_last_run.join(", ")}</code>.</>}
                {" "}Run <code>python -m eval.run --case loan_digital_lending</code>.</div>}
          <p className="small muted">Configuration fingerprint <code>{ev.fingerprint.slice(0, 16)}</code></p>
          {isAdmin && (
            <div className="row">
              <label className="grow">Reason for the change<input value={reason} onChange={(e) => setReason(e.target.value)}
                placeholder="e.g. pilot comparison with the BA team completed" /></label>
              {dep.stage === "advisory"
                ? <button className="primary" disabled={reason.trim().length < 10}
                    onClick={() => act(() => api.setDeployment({ stage: "assisted", require_current_evaluation: true, reason }), "Moved to assisted mode")}>Move to assisted</button>
                : <button disabled={reason.trim().length < 10}
                    onClick={() => act(() => api.setDeployment({ stage: "advisory", require_current_evaluation: true, reason }), "Returned to advisory mode")}>Return to advisory</button>}
            </div>
          )}
        </section>
      )}

      {quality && (
        <section className="card stack">
          <h2>Incorrect recommendations and compliance gaps</h2>
          <div className="metrics">
            <div className="metric"><span className="small muted">Requirement correction rate</span><span className="metric-value">{pct(quality.requirement_correction_rate)}</span></div>
            <div className="metric"><span className="small muted">Legal interpretation corrections</span><span className="metric-value">{pct(quality.interpretation_correction_rate)}</span></div>
            <div className="metric"><span className="small muted">SDLC overrides</span><span className="metric-value">{pct(quality.sdlc_override_rate)}</span></div>
            <div className="metric"><span className="small muted">Gaps found by the agent</span><span className="metric-value">{quality.compliance_gaps_found_by_agent}</span></div>
            <div className="metric main"><span className="small muted">Gaps found after approval</span><span className="metric-value">{quality.compliance_gaps_found_after_approval}</span></div>
          </div>
          <p className="small muted">Gaps found after approval are approved change requests touching regulatory, privacy or audit requirements: compliance
            the assistant (and its reviewers) missed. Rising correction or override rates mean the prompts, rules or knowledge need attention.</p>
          <div className="table-scroll"><table>
            <thead><tr><th>Signal</th><th className="num">Total</th>{Object.keys(quality.trend).slice(-4).map((m) => <th key={m} className="num">{m}</th>)}</tr></thead>
            <tbody>{Object.entries(quality.totals).filter(([k]) => LABELS[k]).map(([k, v]) => (
              <tr key={k}><td className="small">{LABELS[k]}</td><td className="num">{v}</td>
                {Object.values(quality.trend).slice(-4).map((m, i) => <td key={i} className="num">{m[k] ?? 0}</td>)}</tr>
            ))}</tbody>
          </table></div>
          <p className="small muted">Grounded knowledge-base answers reviewed: {quality.kb_answers.corrected ?? 0} corrected, {quality.kb_answers.dismissed ?? 0} dismissed,
            {" "}{quality.kb_answers.confirmed ?? 0} confirmed, {quality.kb_answers.open ?? 0} open.</p>
        </section>
      )}

      <section className="card stack">
        <h2>Financial use cases</h2>
        <p className="small muted">A new domain is enabled once it has approved process knowledge and policies and has passed evaluation, or with a written justification (for example an advisory-only pilot).</p>
        <div className="table-scroll"><table>
          <thead><tr><th>Domain</th><th>Status</th><th>Readiness</th>{isAdmin && <th />}</tr></thead>
          <tbody>{domains.map((d) => (
            <tr key={d.domain}>
              <td><strong>{d.name}</strong><div className="small muted">{d.domain}</div></td>
              <td><span className={`tag ${d.status === "active" ? "ok" : ""}`}>{d.status}</span></td>
              <td className="small">{Object.entries(d.checks).map(([k, v]) => <div key={k}>{v ? "✓" : "✗"} {k.replace(/_/g, " ")}</div>)}</td>
              {isAdmin && <td>{d.status === "active"
                ? <button className="link danger" onClick={() => act(() => api.setDomain(d.domain, false, ""), `${d.name} withdrawn`)}>Withdraw</button>
                : <div className="stack">
                    {!d.ready && <input placeholder="Justification" value={justify[d.domain] ?? ""} onChange={(e) => setJustify({ ...justify, [d.domain]: e.target.value })} />}
                    <button onClick={() => act(() => api.setDomain(d.domain, true, justify[d.domain] ?? ""), `${d.name} enabled`)}>Enable</button>
                  </div>}</td>}
            </tr>
          ))}</tbody>
        </table></div>
      </section>

      {usage && (
        <section className="card stack">
          <h2>Model usage and cost</h2>
          <p>{usage.calls} calls · {usage.input_tokens.toLocaleString()} input and {usage.output_tokens.toLocaleString()} output tokens ·{" "}
            <strong className="num">${usage.cost_usd.toFixed(4)}</strong></p>
          <div className="table-scroll"><table>
            <thead><tr><th>Agent</th><th>Model</th><th className="num">Calls</th><th className="num">Input</th><th className="num">Output</th><th className="num">Cost (USD)</th></tr></thead>
            <tbody>{usage.by_agent_model.map((r) => (
              <tr key={r.agent + r.model}><td className="small">{r.agent}</td><td className="small"><code>{r.model}</code></td><td className="num">{r.calls}</td>
                <td className="num">{r.input_tokens.toLocaleString()}</td><td className="num">{r.output_tokens.toLocaleString()}</td><td className="num">{r.cost_usd.toFixed(4)}</td></tr>
            ))}</tbody>
          </table></div>
        </section>
      )}
    </main>
  );
}
