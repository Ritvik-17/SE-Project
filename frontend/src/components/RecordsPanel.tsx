import { useCallback, useEffect, useState } from "react";
import { api, type AnalystComparison, type ArtifactVersion, type FeedbackRow, type Project, type Usage } from "../api";
import { useMe } from "../auth";
import { useCatalog } from "../catalog";

// System Usability Scale (Brooke, 1996): odd items positive, even items negative; 1 = strongly disagree, 5 = strongly agree
const SUS = [
  "I think that I would like to use this system frequently.",
  "I found the system unnecessarily complex.",
  "I thought the system was easy to use.",
  "I think that I would need the support of a technical person to be able to use this system.",
  "I found the various functions in this system were well integrated.",
  "I thought there was too much inconsistency in this system.",
  "I would imagine that most people would learn to use this system very quickly.",
  "I found the system very cumbersome to use.",
  "I felt very confident using the system.",
  "I needed to learn a lot of things before I could get going with this system.",
];

/** Step 19/20: analyst comparison, stakeholder survey, cost, artefact versions and the accountability record. */
export default function RecordsPanel({ project }: { project: Project }) {
  const pid = project.id;
  const { me } = useMe();
  const catalog = useCatalog();
  const myRoles = me.roles.filter((r) => catalog.role[r]);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [history, setHistory] = useState<ArtifactVersion[]>([]);
  const [feedback, setFeedback] = useState<FeedbackRow[]>([]);
  const [baText, setBaText] = useState("");
  const [cmp, setCmp] = useState<AnalystComparison | null>(null);
  const [sus, setSus] = useState<number[]>(Array(10).fill(3));
  const [survey, setSurvey] = useState({ role: myRoles[0] ?? "", usefulness: 3, trust: 3, comment: "" });
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(() => {
    api.projectUsage(pid).then(setUsage).catch(() => undefined);
    api.artifactHistory(pid).then(setHistory).catch(() => undefined);
    api.feedback(pid).then(setFeedback).catch(() => undefined);
  }, [pid]);
  useEffect(() => { load(); }, [load]);

  async function act(fn: () => Promise<unknown>, done?: string) {
    setError(null); setNote(null);
    try { await fn(); load(); if (done) setNote(done); } catch (e) { setError((e as Error).message); }
  }

  async function downloadPack() {
    const pack = await api.accountabilityPack(pid);
    const url = URL.createObjectURL(new Blob([JSON.stringify(pack, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url; a.download = `accountability-project-${pid}.json`; a.click();
    URL.revokeObjectURL(url);
  }

  const lines = baText.split("\n").map((l) => l.replace(/^\s*([-*•]|\d+[.)])\s*/, "").trim()).filter(Boolean);
  return (
    <div className="stack">
      {error && <div className="alert error">{error}</div>}
      {note && <div className="alert ok">{note}</div>}

      <section className="card stack">
        <h2>Compare with the business analyst</h2>
        <p className="small muted">Paste the requirements the analyst wrote independently, one per line. Each is matched one-to-one to the
          assistant's extracted requirements by meaning (cosine similarity ≥ 0.80). The result is stored as a shadow-comparison evaluation.</p>
        <textarea rows={8} value={baText} onChange={(e) => setBaText(e.target.value)}
          placeholder={"The system must verify the applicant's PAN with the income-tax database.\nThe applicant must be shown the Key Fact Statement before signing."} />
        <div><button className="primary" disabled={!lines.length}
          onClick={() => act(async () => setCmp(await api.analystComparison(pid, lines)))}>Compare {lines.length || ""} requirement{lines.length === 1 ? "" : "s"}</button></div>
        {cmp && (
          <div className="stack">
            <div className="metrics">
              <div className="metric"><span className="small muted">Analyst items</span><span className="metric-value">{cmp.analyst_requirements}</span></div>
              <div className="metric"><span className="small muted">AI items</span><span className="metric-value">{cmp.ai_requirements}</span></div>
              <div className="metric"><span className="small muted">AI found of analyst's</span><span className="metric-value">{Math.round(cmp.agreement.recall * 100)}%</span></div>
              <div className="metric"><span className="small muted">AI items analyst also had</span><span className="metric-value">{Math.round(cmp.agreement.precision * 100)}%</span></div>
              <div className="metric main"><span className="small muted">Agreement F1</span><span className="metric-value">{cmp.agreement.f1.toFixed(2)}</span></div>
            </div>
            <details><summary>Only the analyst found ({cmp.only_analyst.length})</summary>
              <ul className="issues">{cmp.only_analyst.map((s, i) => <li key={i}>{s}</li>)}</ul></details>
            <details><summary>Only the assistant found ({cmp.only_ai.length}): check whether these are useful or hallucinated</summary>
              <ul className="issues">{cmp.only_ai.map((r) => <li key={r.id}><code>{r.id}</code> {r.statement}</li>)}</ul></details>
            <details><summary>Matched ({cmp.matched.length})</summary>
              <ul className="issues">{cmp.matched.map((m, i) => <li key={i}><code>{m.ai}</code> ↔ {m.analyst} <span className="muted small">({m.similarity.toFixed(2)})</span></li>)}</ul></details>
          </div>
        )}
      </section>

      <section className="card stack">
        <h2>Stakeholder survey</h2>
        <p className="small muted">1 = strongly disagree, 5 = strongly agree. Scored with the System Usability Scale (0–100; 68 is average).</p>
        <ol className="stack small">{SUS.map((q, i) => (
          <li key={i} className="row">
            <span className="grow">{q}</span>
            <span className="nowrap">{[1, 2, 3, 4, 5].map((v) => (
              <label key={v} className="check-inline"><input type="radio" name={`sus-${i}`} checked={sus[i] === v}
                onChange={() => setSus(sus.map((x, j) => (j === i ? v : x)))} />{v}</label>))}</span>
          </li>
        ))}</ol>
        <div className="row">
          <label>Answering as<select value={survey.role} onChange={(e) => setSurvey({ ...survey, role: e.target.value })}>
            {myRoles.map((r) => <option key={r} value={r}>{catalog.role[r].name}</option>)}</select></label>
          <label>Usefulness (1–5)<input type="number" min={1} max={5} value={survey.usefulness} onChange={(e) => setSurvey({ ...survey, usefulness: Number(e.target.value) })} /></label>
          <label>Trust (1–5)<input type="number" min={1} max={5} value={survey.trust} onChange={(e) => setSurvey({ ...survey, trust: Number(e.target.value) })} /></label>
          <label className="grow">Comment<input value={survey.comment} onChange={(e) => setSurvey({ ...survey, comment: e.target.value })} /></label>
        </div>
        <div><button className="primary" disabled={!survey.role}
          onClick={() => act(async () => { const r = await api.submitFeedback(pid, { ...survey, sus }); setNote(`Thank you. SUS score ${r.sus_score}.`); })}>Submit survey</button></div>
        {feedback.length > 0 && (
          <table><thead><tr><th>Role</th><th className="num">SUS</th><th className="num">Usefulness</th><th className="num">Trust</th><th>Comment</th></tr></thead>
            <tbody>{feedback.map((f, i) => (
              <tr key={i}><td className="small">{catalog.role[f.role]?.name ?? f.role}</td><td className="num">{f.sus_score}</td><td className="num">{f.usefulness}</td>
                <td className="num">{f.trust}</td><td className="small muted">{f.comment}</td></tr>))}</tbody></table>
        )}
      </section>

      <section className="card stack">
        <h2>Artefact versions</h2>
        {history.length === 0 ? <p className="muted small">No documents generated yet.</p> : (
          <table><thead><tr><th className="num">Version</th><th>Status</th><th>Generated</th><th>Superseded</th><th>Documents</th></tr></thead>
            <tbody>{history.map((v) => (
              <tr key={v.version}><td className="num">v{v.version}</td>
                <td><span className={`tag ${v.status === "advisory" ? "sev-medium" : "ok"}`}>{v.status}</span></td>
                <td className="small">{new Date(v.created_at).toLocaleString()}</td>
                <td className="small">{v.superseded_at ? new Date(v.superseded_at).toLocaleString() : "current"}</td>
                <td className="small muted">{v.kinds.length}</td></tr>))}</tbody></table>
        )}
      </section>

      <section className="card stack">
        <div className="section-head"><h2>Model usage</h2>
          {usage && <span className="metric-inline">${usage.cost_usd.toFixed(4)}</span>}</div>
        {usage && <p className="small">{usage.calls} model calls · {usage.input_tokens.toLocaleString()} input · {usage.output_tokens.toLocaleString()} output tokens</p>}
        {usage && usage.by_agent_model.length > 0 && (
          <div className="table-scroll"><table>
            <thead><tr><th>Agent</th><th>Model</th><th className="num">Calls</th><th className="num">Tokens</th><th className="num">USD</th></tr></thead>
            <tbody>{usage.by_agent_model.map((r) => (
              <tr key={r.agent + r.model}><td className="small">{r.agent}</td><td className="small"><code>{r.model}</code></td><td className="num">{r.calls}</td>
                <td className="num">{(r.input_tokens + r.output_tokens).toLocaleString()}</td><td className="num">{r.cost_usd.toFixed(4)}</td></tr>))}</tbody>
          </table></div>
        )}
      </section>

      <section className="card stack">
        <div className="section-head"><h2>Accountability record</h2>
          <button onClick={() => act(downloadPack, "Accountability pack downloaded")}>Download</button></div>
        <p className="small muted">One JSON file with every prompt and model response, the knowledge-base evidence each agent retrieved (with document
          versions), agent decisions, human edits and approvals, change requests, readiness reviews, every artefact version, evaluations
          and the model and knowledge versions used. Available to auditors, compliance and the project manager; the export itself is audited.</p>
      </section>
    </div>
  );
}
