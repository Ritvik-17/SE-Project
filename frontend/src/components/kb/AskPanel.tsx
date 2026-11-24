import { useEffect, useState, type FormEvent } from "react";
import { useMe } from "../../auth";
import { api, type GroundedAnswerResult, type ReviewQueueItem } from "../../api";
import { useCatalog } from "../../catalog";

const STEPS = ["Classify", "Retrieve", "Give evidence", "Generate", "Cite & score", "Escalate if weak"];

/** Step 6 for stakeholder questions: a grounded answer with citations, a confidence score and escalation. */
export function AskPanel() {
  const catalog = useCatalog();
  const [q, setQ] = useState("How long must rejected loan applications be kept?");
  const who = useMe().me.username;
  const [domain, setDomain] = useState("loan_processing");
  const [jur, setJur] = useState("IN");
  const [res, setRes] = useState<GroundedAnswerResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(null);
    try { setRes(await api.kbAsk({ question: q, asked_by: who.trim(), domain, jurisdiction: jur })); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }

  return (
    <div className="stack">
      <form className="card" onSubmit={ask}>
        <h2>Ask the knowledge base</h2>
        <ol className="track" aria-label="Pipeline">{STEPS.map((s) => <li key={s} className="done">{s}</li>)}</ol>
        <p className="muted small">Answers use only approved, in-force sources. Each claim cites its passage. Weak or uncited answers go to the review queue for a compliance reviewer.</p>
        <label htmlFor="ask-q">Question<textarea id="ask-q" rows={2} value={q} onChange={(e) => setQ(e.target.value)} /></label>
        <div className="row">
          <label className="grow" htmlFor="ask-d">Domain<select id="ask-d" value={domain} onChange={(e) => setDomain(e.target.value)}>
            {catalog.domains.filter((d) => d.status === "active").map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
          <label className="grow" htmlFor="ask-j">Jurisdiction<select id="ask-j" value={jur} onChange={(e) => setJur(e.target.value)}>
            <option value="IN">India</option><option value="EU">European Union</option><option value="GLOBAL">Global</option></select></label>
          
        </div>
        <div><button className="primary" type="submit" disabled={busy || !q.trim() || !who.trim()}>{busy ? "Retrieving and answering…" : "Ask"}</button></div>
      </form>
      {error && <div className="alert error">{error}</div>}
      {res && <AnswerView res={res} />}
    </div>
  );
}

function AnswerView({ res }: { res: GroundedAnswerResult }) {
  return (
    <section className="card">
      <div className="section-head">
        <h2>Answer</h2>
        <span className={`tag ${res.escalated ? "sev-medium" : "ok"}`}>{res.escalated ? `escalated · review #${res.review_id}` : "grounded"}</span>
      </div>
      <p>{res.answer}</p>
      <div className="metrics" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
        <div className="metric main"><span className="eyebrow">confidence</span><span className="metric-value">{Math.round(res.confidence * 100)}<span className="small muted">%</span></span></div>
        <div className="metric"><span className="eyebrow">model</span><span className="metric-value">{Math.round(res.components.llm * 100)}<span className="small muted">%</span></span></div>
        <div className="metric"><span className="eyebrow">claims cited</span><span className="metric-value">{Math.round(res.components.citation_coverage * 100)}<span className="small muted">%</span></span></div>
        <div className="metric"><span className="eyebrow">evidence</span><span className="metric-value" style={{ fontSize: "1.1rem" }}>{res.components.evidence_strength}</span></div>
      </div>
      <p className="note">Confidence = model confidence × evidence factor (strong 1.0, weak 0.6, none 0.25) × share of claims with a valid citation.</p>
      {res.escalated && <div className="alert warn">Sent for review: {res.escalation_reasons.join("; ")}</div>}
      <h3>Claims</h3>
      <ul className="issues">
        {res.claims.map((c, i) => (
          <li key={i} className={`stripe ${c.refs.length ? "low" : "high"}`}>
            {c.text}
            <div className="small muted">{c.citations.length ? c.citations.join("; ") : "no valid citation"}
              {c.invalid_refs.length > 0 && <span className="danger-text"> · cited passages that were not retrieved: {c.invalid_refs.join(", ")}</span>}</div>
          </li>
        ))}
      </ul>
      <p className="small muted">Classified as <code>{res.classification.intent}</code> → searched {res.classification.collections.join(", ") || "nothing"} with “{res.classification.search_queries.join("”, “")}”.</p>
    </section>
  );
}

/** Escalated outputs waiting for a human (step 6.6). */
export function ReviewQueue({ onChanged }: { onChanged: () => void }) {
  const catalog = useCatalog();
  const [items, setItems] = useState<ReviewQueueItem[] | null>(null);
  const { me } = useMe();
  const actor = me.username;
  const [role, setRole] = useState("compliance_legal");
  const [text, setText] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const load = () => api.kbReviewQueue().then(setItems).catch((e: Error) => setError(e.message));
  useEffect(() => { load(); }, []);

  async function resolve(id: number, outcome: string) {
    setError(null);
    try { await api.kbResolveReview(id, { actor: actor.trim(), role, outcome, resolution: text[id] ?? "" }); await load(); onChanged(); }
    catch (err) { setError((err as Error).message); }
  }

  if (!items) return <p className="muted">Loading…</p>;
  return (
    <section className="stack">
      <div className="row">
        <div className="grow small muted">Reviewing as <strong>{me.display_name}</strong></div>
        <label className="grow" htmlFor="rq-role">Role<select id="rq-role" value={role} onChange={(e) => setRole(e.target.value)}>
          {catalog.roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
      </div>
      {error && <div className="alert error">{error}</div>}
      {items.length === 0 ? <div className="empty">Nothing waiting for review.</div> : items.map((it) => (
        <article key={it.id} className="card stripe high">
          <div className="section-head"><h3>#{it.id} {it.subject}</h3><span className="small muted">asked by {it.requested_by}</span></div>
          <p className="small"><strong>AI answer ({Math.round(it.payload.confidence * 100)}%):</strong> {it.payload.answer}</p>
          <p className="small warn-text">{it.reasons.join("; ")}</p>
          <label htmlFor={`rq-${it.id}`}>Corrected answer (required to correct)
            <textarea id={`rq-${it.id}`} rows={2} value={text[it.id] ?? ""} onChange={(e) => setText({ ...text, [it.id]: e.target.value })} /></label>
          <div className="row">
            <button disabled={!actor.trim()} onClick={() => resolve(it.id, "confirmed")}>Confirm answer</button>
            <button className="primary" disabled={!actor.trim() || !(text[it.id] ?? "").trim()} onClick={() => resolve(it.id, "corrected")}>Save correction</button>
            <button className="link" disabled={!actor.trim()} onClick={() => resolve(it.id, "dismissed")}>Dismiss</button>
          </div>
        </article>
      ))}
    </section>
  );
}
