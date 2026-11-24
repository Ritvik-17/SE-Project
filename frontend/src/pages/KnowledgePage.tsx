import { Fragment, useCallback, useEffect, useState, type FormEvent } from "react";
import { useMe } from "../auth";
import { Link } from "react-router-dom";
import { api, type KbDetail, type KbDoc, type KbHit, type KbImpact, type KbMeta } from "../api";
import { useCatalog } from "../catalog";
import { AskPanel, ReviewQueue } from "../components/kb/AskPanel";

const VIEWS = ["Library", "Approvals", "Add item", "Ask", "Review queue", "Retrieval tester", "Change impact"] as const;
type View = (typeof VIEWS)[number];

/** Step 5: authorised, version-controlled knowledge base. Step 6: retrieval that grounds the agents. */
export default function KnowledgePage() {
  const [meta, setMeta] = useState<KbMeta | null>(null);
  const [docs, setDocs] = useState<KbDoc[]>([]);
  const [impacts, setImpacts] = useState<KbImpact[]>([]);
  const [queue, setQueue] = useState(0);
  const [view, setView] = useState<View>("Library");
  const [openId, setOpenId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.kbDocuments().then(setDocs).catch((e: Error) => setError(e.message));
    api.kbImpacts().then(setImpacts).catch(() => undefined);
    api.kbReviewQueue().then((q) => setQueue(q.length)).catch(() => undefined);
  }, []);
  useEffect(() => { api.kbMeta().then(setMeta).catch((e: Error) => setError(e.message)); load(); }, [load]);

  if (!meta) return <main className="page">{error ? <div className="alert error">{error}</div> : <span className="muted">Loading…</span>}</main>;
  const drafts = docs.filter((d) => d.status === "draft");
  const counts: Partial<Record<View, number>> = { Approvals: drafts.length, "Review queue": queue, "Change impact": impacts.length };

  return (
    <main className="page">
      <header className="page-head">
        <span className="eyebrow">Steps 5–6 · authorised knowledge, retrieval-grounded generation</span>
        <h1>Knowledge base</h1>
        <p className="muted">
          Regulations, policies, standards, terminology, guidelines, templates and approved projects that ground the agents.
          Every item records its source, jurisdiction, effective date, version and applicability. An item is searchable
          only after its owner approves it, and only while it is in force.
        </p>
      </header>
      {error && <div className="alert error">{error}</div>}

      <CollectionSummary meta={meta} docs={docs} />

      <div className="tabs" role="tablist">
        {VIEWS.map((v) => (
          <button key={v} role="tab" aria-selected={view === v} className={view === v ? "active" : ""} onClick={() => setView(v)}>
            {v}{counts[v] ? <span className="count">{counts[v]}</span> : null}
          </button>
        ))}
      </div>

      {view === "Library" && <Library meta={meta} docs={docs} onOpen={setOpenId} />}
      {view === "Approvals" && <Library meta={meta} docs={drafts} onOpen={setOpenId} emptyText="No drafts waiting for approval." />}
      {view === "Add item" && <SubmitForm meta={meta} onSubmitted={(id) => { load(); setOpenId(id); setView("Approvals"); }} />}
      {view === "Ask" && <AskPanel />}
      {view === "Review queue" && <ReviewQueue onChanged={load} />}
      {view === "Retrieval tester" && <Tester meta={meta} />}
      {view === "Change impact" && <Impacts impacts={impacts} onResolved={load} />}

      {openId !== null && <DocumentPanel id={openId} meta={meta} onClose={() => setOpenId(null)} onChanged={load} />}
    </main>
  );
}

function CollectionSummary({ meta, docs }: { meta: KbMeta; docs: KbDoc[] }) {
  return (
    <div className="kb-collections">
      {meta.collections.map((c) => {
        const mine = docs.filter((d) => d.collection === c.id);
        const inForce = mine.filter((d) => d.in_force).length;
        const drafts = mine.filter((d) => d.status === "draft").length;
        return (
          <div key={c.id} className="kb-collection" title={c.description}>
            <span className="eyebrow">{c.searchable ? "searched" : "looked up"}</span>
            <strong>{c.name}</strong>
            <span className="small num">
              <span className="metric-inline">{inForce}</span> in force{drafts > 0 && <> · <span className="warn-text">{drafts} draft</span></>}
            </span>
          </div>
        );
      })}
    </div>
  );
}

const STATUS_CLASS: Record<string, string> = { active: "ok", draft: "sev-medium", superseded: "", withdrawn: "sev-high", rejected: "sev-high" };

function Library({ meta, docs, onOpen, emptyText }: { meta: KbMeta; docs: KbDoc[]; onOpen: (id: number) => void; emptyText?: string }) {
  const catalog = useCatalog();
  const [collection, setCollection] = useState("");
  const [showOld, setShowOld] = useState(false);
  const rows = docs.filter((d) => (!collection || d.collection === collection) && (showOld || !["superseded", "rejected", "withdrawn"].includes(d.status)));
  const colName = Object.fromEntries(meta.collections.map((c) => [c.id, c.name]));
  return (
    <section className="stack">
      <div className="row center-y">
        <label className="row center-y" htmlFor="kb-filter">Collection
          <select id="kb-filter" value={collection} onChange={(e) => setCollection(e.target.value)}>
            <option value="">All collections</option>
            {meta.collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <label className="row center-y" style={{ flexDirection: "row" }}>
          <input type="checkbox" checked={showOld} onChange={(e) => setShowOld(e.target.checked)} /> Show superseded, withdrawn and rejected
        </label>
      </div>
      {rows.length === 0 ? <div className="empty">{emptyText ?? "No items yet. Seed the knowledge base or add an item."}</div> : (
        <div className="table-scroll">
          <table>
            <thead><tr><th>Item</th><th>Source</th><th>Jurisdiction</th><th>Version</th><th>In force</th><th>Applies to</th><th>Status</th><th className="num">Passages</th></tr></thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.id} className="clickable" onClick={() => onOpen(d.id)}>
                  <td><button className="link" style={{ padding: 0, textAlign: "left", whiteSpace: "normal" }}>{d.title}</button>
                    <div className="muted small">{colName[d.collection]} · <code>{d.doc_key}</code></div></td>
                  <td className="small">{d.source.issuer}<div><span className="tag">{d.source.license.replace("_", " ")}</span></div></td>
                  <td className="small">{d.jurisdictions.join(", ")}</td>
                  <td><code>{d.version}</code></td>
                  <td className="small num">{d.effective_from}{d.effective_to ? ` → ${d.effective_to}` : " →"}
                    {d.review_overdue && <div><span className="tag sev-medium">review overdue</span></div>}</td>
                  <td className="small">{d.applicability.domains[0] === "all" ? <span className="muted">All domains</span>
                    : d.applicability.domains.map((x) => <span key={x} className="chip">{catalog.domain[x]?.code ?? x}</span>)}</td>
                  <td><span className={`tag ${STATUS_CLASS[d.status]}`}>{d.status}</span>{d.in_force && d.status !== "active" && <div className="small muted">still in force</div>}</td>
                  <td className="num">{d.chunk_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function DocumentPanel({ id, meta, onClose, onChanged }: { id: number; meta: KbMeta; onClose: () => void; onChanged: () => void }) {
  const catalog = useCatalog();
  const [detail, setDetail] = useState<KbDetail | null>(null);
  const actor = useMe().me.username;
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showText, setShowText] = useState(false);

  const load = useCallback(() => api.kbDocument(id).then(setDetail).catch((e: Error) => setError(e.message)), [id]);
  useEffect(() => { load(); }, [load]);
  if (!detail) return null;
  const d = detail.document;
  const col = meta.collections.find((c) => c.id === d.collection)!;
  const defaultRole = d.approved_role ?? col.approver_roles[0];

  async function act(fn: () => Promise<unknown>) {
    setBusy(true); setError(null);
    try { await fn(); await load(); onChanged(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <div className="panel-backdrop" onClick={onClose}>
      <aside className="panel" role="dialog" aria-label={d.title} onClick={(e) => e.stopPropagation()}>
        <div className="section-head">
          <span className="eyebrow">{col.name}</span>
          <button className="link" onClick={onClose}>Close</button>
        </div>
        <h2>{d.title}</h2>
        <div className="chips"><span className={`tag ${STATUS_CLASS[d.status]}`}>{d.status}</span>{d.in_force && <span className="tag ok">in force</span>}
          <span className="tag">v{d.version}</span><code className="small">{d.doc_key}</code></div>
        {error && <div className="alert error">{error}</div>}

        <dl className="kv">
          <dt>Source</dt><dd>{d.source.issuer}{d.source.url && <> · <a href={d.source.url} target="_blank" rel="noreferrer">link</a></>}
            <div className="small muted">{d.source.license.replace("_", " ")} · sha256 <code>{d.source.sha256.slice(0, 12)}…</code></div></dd>
          <dt>Jurisdiction</dt><dd>{d.jurisdictions.map((j) => meta.jurisdictions[j] ?? j).join(", ")}</dd>
          <dt>Effective</dt><dd className="num">{d.effective_from} → {d.effective_to ?? "open"}{d.review_due && <span className="muted"> · review by {d.review_due}</span>}</dd>
          <dt>Version</dt><dd>{d.version} <span className="muted small">({detail.versions.length} version{detail.versions.length > 1 ? "s" : ""})</span></dd>
          <dt>Applicability</dt><dd>
            {d.applicability.domains[0] === "all" ? "All domains" : d.applicability.domains.map((x) => catalog.domain[x]?.name ?? x).join(", ")}
            {d.applicability.entity_types?.length ? <div className="small muted">Entities: {d.applicability.entity_types.join(", ")}</div> : null}
            {d.applicability.roles?.length ? <div className="small muted">Roles: {d.applicability.roles.map((r) => catalog.role[r]?.name ?? r).join(", ")}</div> : null}
          </dd>
          <dt>Authorisation</dt><dd className="small">Submitted by {d.submitted_by}{d.approved_by && <> · approved by {d.approved_by} as {catalog.role[d.approved_role ?? ""]?.name ?? d.approved_role}</>}</dd>
          <dt>Indexing</dt><dd className="small">{d.section_count} sections · {d.chunk_count} passages{d.embedding_model && <> · <code>{d.embedding_model}</code></>}
            {Object.keys(d.redactions).length > 0 && <> · masked {Object.entries(d.redactions).map(([k, v]) => `${k}×${v}`).join(", ")}</>}</dd>
          {d.notes && <><dt>Notes</dt><dd className="small">{d.notes}</dd></>}
        </dl>

        <section className="stack tight">
          <h3>Changes {detail.diff_vs ? `since v${detail.diff_vs}` : "(first version)"}</h3>
          <div className="chips small">
            <span className="chip ok">+{detail.diff.added.length} added</span>
            <span className="chip sev-medium">{detail.diff.changed.length} changed</span>
            <span className="chip sev-high">−{detail.diff.removed.length} removed</span>
            <span className="chip">{detail.diff.unchanged} unchanged</span>
          </div>
          {detail.diff_vs && (detail.diff.changed.length + detail.diff.added.length + detail.diff.removed.length > 0) && (
            <ul className="small" style={{ margin: 0, paddingLeft: "1.1rem" }}>
              {detail.diff.changed.map((s) => <li key={s}><span className="warn-text">changed</span> {s}</li>)}
              {detail.diff.added.map((s) => <li key={s}><span className="ok-text">added</span> {s}</li>)}
              {detail.diff.removed.map((s) => <li key={s}><span className="danger-text">removed</span> {s}</li>)}
            </ul>
          )}
        </section>

        {detail.versions.length > 1 && (
          <section className="stack tight">
            <h3>Version history</h3>
            <ol className="versions">
              {detail.versions.map((v) => (
                <li key={v.id} className={v.id === d.id ? "current" : ""}>
                  <code>v{v.version}</code> <span className={`tag ${STATUS_CLASS[v.status]}`}>{v.status}</span>
                  <span className="small muted num"> {v.effective_from} → {v.effective_to ?? "open"}</span>
                </li>
              ))}
            </ol>
          </section>
        )}

        <section className="stack tight">
          <div className="section-head"><h3>Structure</h3><button className="link" onClick={() => setShowText(!showText)}>{showText ? "Hide text" : "Show text"}</button></div>
          {showText ? <pre className="masked">{detail.content}</pre> : (
            <ul className="small" style={{ margin: 0, paddingLeft: "1.1rem", maxHeight: 200, overflow: "auto" }}>
              {detail.sections.map((s, i) => <li key={i}>{s.path.join(" › ") || "(preamble)"} <span className="muted">· {s.passages}</span></li>)}
            </ul>
          )}
        </section>

        {(d.status === "draft" || d.status === "active") && (
          <section className="card stack tight">
            <h3>{d.status === "draft" ? "Approve this version" : "Withdraw this version"}</h3>
            {d.status === "draft" && <p className="note">Approval by {col.approver_roles.map((r) => catalog.role[r]?.name).join(" or ")}. Approving supersedes the current version from v{d.version}'s effective date.</p>}
            <div className="row">
              
              {d.status === "draft" && <label className="grow" htmlFor="kb-role">As role
                <select id="kb-role" defaultValue={defaultRole}>{col.approver_roles.map((r) => <option key={r} value={r}>{catalog.role[r]?.name}</option>)}</select></label>}
            </div>
            <label htmlFor="kb-reason">{d.status === "draft" ? "Reason (required to reject)" : "Reason (required)"}<input id="kb-reason" value={reason} onChange={(e) => setReason(e.target.value)} /></label>
            <div className="row">
              {d.status === "draft" ? <>
                <button className="primary" disabled={busy || !actor.trim()} onClick={() => act(() =>
                  api.kbApprove(d.id, actor.trim(), (document.getElementById("kb-role") as HTMLSelectElement).value))}>Approve</button>
                <button disabled={busy || !actor.trim() || !reason.trim()} onClick={() => act(() => api.kbReject(d.id, actor.trim(), reason))}>Reject</button>
              </> : <button className="danger" disabled={busy || !actor.trim() || !reason.trim()} onClick={() => act(() => api.kbWithdraw(d.id, actor.trim(), reason))}>Withdraw</button>}
            </div>
          </section>
        )}
      </aside>
    </div>
  );
}

function SubmitForm({ meta, onSubmitted }: { meta: KbMeta; onSubmitted: (id: number) => void }) {
  const catalog = useCatalog();
  const [f, setF] = useState({ doc_key: "", collection: "regulation", title: "", issuer: "", source_url: "", license: "full_text",
    version: "", effective_from: "", review_due: "", notes: "", submitted_by: useMe().me.username });
  const [jur, setJur] = useState<string[]>(["IN"]);
  const [domains, setDomains] = useState<string[]>(["all"]);
  const [mode, setMode] = useState<"text" | "file">("file");
  const [content, setContent] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const toggle = (list: string[], v: string, on: boolean) => (on ? [...list.filter((x) => x !== "all"), v] : list.filter((x) => x !== v));

  async function submit(e: FormEvent) {
    e.preventDefault();
    const metadata = {
      doc_key: f.doc_key.trim(), collection: f.collection, title: f.title.trim(), issuer: f.issuer.trim(),
      source_url: f.source_url.trim() || null, license: f.license, jurisdictions: jur, version: f.version.trim(),
      effective_from: f.effective_from, review_due: f.review_due || null, notes: f.notes || null,
      applicability: { domains: domains.length ? domains : ["all"] },
    };
    const fd = new FormData();
    fd.append("metadata", JSON.stringify(metadata));
    fd.append("submitted_by", f.submitted_by.trim());
    if (mode === "file" && file) fd.append("file", file); else fd.append("content", content);
    setBusy(true); setError(null);
    try { onSubmitted((await api.kbSubmit(fd)).document.id); } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }

  const col = meta.collections.find((c) => c.id === f.collection)!;
  return (
    <form className="card" onSubmit={submit}>
      <h2>Add an item or a new version</h2>
      <p className="note">Use the same document key as an existing item to submit a new version; the approver sees a section-by-section diff.
        Submissions are drafts until {col.approver_roles.map((r) => catalog.role[r]?.name).join(" or ")} approves.</p>
      {error && <div className="alert error">{error}</div>}
      <div className="row">
        <label className="grow" htmlFor="f-col">Collection
          <select id="f-col" value={f.collection} onChange={set("collection")}>{meta.collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        <label className="grow" htmlFor="f-key">Document key<input id="f-key" value={f.doc_key} onChange={set("doc_key")} placeholder="rbi-kyc-master-direction" required pattern="[a-z0-9][a-z0-9\-]{2,119}" /></label>
      </div>
      <label htmlFor="f-title">Title<input id="f-title" value={f.title} onChange={set("title")} required /></label>
      <fieldset><legend>Source</legend>
        <div className="row">
          <label className="grow" htmlFor="f-issuer">Issuer<input id="f-issuer" value={f.issuer} onChange={set("issuer")} placeholder="Reserve Bank of India" required /></label>
          <label className="grow" htmlFor="f-url">Source URL or citation<input id="f-url" value={f.source_url} onChange={set("source_url")} placeholder="https://…" /></label>
          <label htmlFor="f-lic">Licence<select id="f-lic" value={f.license} onChange={set("license")}>{meta.licenses.map((l) => <option key={l} value={l}>{l.replace("_", " ")}</option>)}</select></label>
        </div>
      </fieldset>
      <fieldset><legend>Jurisdiction</legend>
        <div className="checks">{Object.entries(meta.jurisdictions).map(([k, v]) => (
          <label key={k}><input type="checkbox" checked={jur.includes(k)} onChange={(e) => setJur(e.target.checked ? [...jur, k] : jur.filter((x) => x !== k))} />{v}</label>))}</div>
      </fieldset>
      <fieldset><legend>Version and effective dates</legend>
        <div className="row">
          <label className="grow" htmlFor="f-ver">Version<input id="f-ver" value={f.version} onChange={set("version")} placeholder="as printed on the document" required /></label>
          <label className="grow" htmlFor="f-from">In force from<input id="f-from" type="date" value={f.effective_from} onChange={set("effective_from")} required /></label>
          <label className="grow" htmlFor="f-review">Review by<input id="f-review" type="date" value={f.review_due} onChange={set("review_due")} /></label>
        </div>
      </fieldset>
      <fieldset><legend>Applicability (domains)</legend>
        <div className="checks">
          <label><input type="checkbox" checked={domains.includes("all")} onChange={(e) => setDomains(e.target.checked ? ["all"] : [])} />All domains</label>
          {catalog.domains.map((d) => <label key={d.id}><input type="checkbox" checked={domains.includes(d.id)} onChange={(e) => setDomains(toggle(domains, d.id, e.target.checked))} />{d.name}</label>)}
        </div>
      </fieldset>
      <div className="segmented">
        <button type="button" className={mode === "file" ? "active" : ""} onClick={() => setMode("file")}>Upload file</button>
        <button type="button" className={mode === "text" ? "active" : ""} onClick={() => setMode("text")}>Paste text</button>
      </div>
      {mode === "file" ? <input id="f-file" type="file" accept=".pdf,.docx,.md,.txt,.yaml,.yml" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        : <textarea id="f-text" rows={8} value={content} onChange={(e) => setContent(e.target.value)} />}
      <div className="row">
        
        <label className="grow" htmlFor="f-notes">Notes<input id="f-notes" value={f.notes} onChange={set("notes")} /></label>
      </div>
      <p className="note">Documents are split at headings and numbered clauses into parent sections and searchable passages,
        each prefixed with its location, then embedded. Unchanged passages reuse cached embeddings.</p>
      <div><button className="primary" type="submit" disabled={busy || jur.length === 0 || (mode === "file" ? !file : !content.trim())}>
        {busy ? "Chunking and embedding…" : "Submit draft"}</button></div>
    </form>
  );
}

function Tester({ meta }: { meta: KbMeta }) {
  const catalog = useCatalog();
  const [q, setQ] = useState("Who must approve changes to customer bank account details?");
  const [domain, setDomain] = useState("loan_processing");
  const [jur, setJur] = useState("IN");
  const [asOf, setAsOf] = useState("");
  const [cols, setCols] = useState<string[]>([]);
  const [hits, setHits] = useState<KbHit[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const searchable = meta.collections.filter((c) => c.searchable);

  async function run(e: FormEvent) {
    e.preventDefault(); setError(null);
    try { setHits(await api.kbSearch({ query: q, domain: domain || undefined, jurisdiction: jur || undefined, as_of: asOf || undefined, collections: cols.length ? cols : undefined })); }
    catch (err) { setError((err as Error).message); }
  }

  return (
    <div className="stack">
      <form className="card" onSubmit={run}>
        <h2>Retrieval tester</h2>
        <p className="muted small">Runs the same pipeline the agents use: metadata filters, vector + keyword search, rank fusion, reranking, parent expansion.</p>
        <label htmlFor="t-q">Query<input id="t-q" value={q} onChange={(e) => setQ(e.target.value)} /></label>
        <div className="row">
          <label className="grow" htmlFor="t-d">Domain<select id="t-d" value={domain} onChange={(e) => setDomain(e.target.value)}>
            <option value="">Any</option>{catalog.domains.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
          <label className="grow" htmlFor="t-j">Jurisdiction<select id="t-j" value={jur} onChange={(e) => setJur(e.target.value)}>
            <option value="">Any</option>{Object.entries(meta.jurisdictions).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          <label className="grow" htmlFor="t-a">As of date<input id="t-a" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} /></label>
        </div>
        <div className="checks">{searchable.map((c) => (
          <label key={c.id}><input type="checkbox" checked={cols.includes(c.id)} onChange={(e) => setCols(e.target.checked ? [...cols, c.id] : cols.filter((x) => x !== c.id))} />{c.name}</label>))}</div>
        <div><button className="primary" type="submit" disabled={!q.trim()}>Search</button></div>
      </form>
      {error && <div className="alert error">{error}</div>}
      {hits && (hits.length === 0 ? <div className="empty">No applicable passages. Check the filters, or whether items are approved and in force.</div> : (
        <div className="table-scroll">
          <table>
            <thead><tr><th>#</th><th>Citation</th><th>Strength</th><th className="num">Vector</th><th className="num">Keyword</th><th className="num">RRF</th><th className="num">Rerank</th></tr></thead>
            <tbody>
              {hits.map((h, i) => (
                <Fragment key={h.ref}>
                  <tr className={`clickable stripe-row ${h.strength}`} onClick={() => setOpen(open === h.ref ? null : h.ref)}>
                    <td className="num">{i + 1}</td>
                    <td><strong>{h.citation}</strong><div className="small muted">{h.issuer} · {h.jurisdictions.join(", ")} · from {h.effective_from} · <code>{h.ref}</code></div>
                      <div className="small">{h.passage.slice(0, 180)}{h.passage.length > 180 ? "…" : ""}</div></td>
                    <td><span className={`tag ${h.strength === "strong" ? "ok" : h.strength === "weak" ? "sev-medium" : ""}`}>{h.strength}</span></td>
                    <td className="num">{h.scores.vector_rank ?? "—"}</td>
                    <td className="num">{h.scores.lexical_rank ?? "—"}</td>
                    <td className="num">{h.scores.rrf.toFixed(4)}</td>
                    <td className="num">{h.scores.rerank !== null ? h.scores.rerank.toFixed(3) : <span className="muted">{h.scores.method}</span>}</td>
                  </tr>
                  {open === h.ref && <tr><td /><td colSpan={6}><span className="eyebrow">Parent section given to the agent</span><pre className="masked">{h.context}</pre></td></tr>}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

function Impacts({ impacts, onResolved }: { impacts: KbImpact[]; onResolved: () => void }) {
  const actor = useMe().me.username;
  if (impacts.length === 0) return <div className="empty">No open regulatory-change impacts. When a cited document is superseded or withdrawn, affected projects appear here.</div>;
  return (
    <section className="stack">
      
      <ul className="issues">
        {impacts.map((i) => (
          <li key={i.id} className="stripe high row between">
            <span><Link to={`/projects/${i.project_id}`}>Project {i.project_id}</Link> cites <code>{i.doc_key}</code> v{i.old_version}, which was {i.change}
              {i.new_version && <> by v{i.new_version}</>}. Passages: {i.cited_refs.join(", ")}</span>
            <button disabled={!actor.trim()} onClick={() => api.kbResolveImpact(i.id, actor.trim(), "Re-evaluated").then(onResolved)}>Mark re-evaluated</button>
          </li>
        ))}
      </ul>
    </section>
  );
}
