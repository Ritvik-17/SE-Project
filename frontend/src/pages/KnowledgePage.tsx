import { Fragment, useCallback, useEffect, useState, type FormEvent } from "react";
import { useMe } from "../auth";
import { Link } from "react-router-dom";
import { api, type KbDetail, type KbDoc, type KbHit, type KbImpact, type KbMeta } from "../api";
import { useCatalog } from "../catalog";
import { AskPanel, ReviewQueue } from "../components/kb/AskPanel";

const VIEWS = ["Documents", "Ask", "Advanced"] as const;
type View = (typeof VIEWS)[number];

/** Step 5: authorised, version-controlled knowledge base. Step 6: retrieval that grounds the agents. */
export default function KnowledgePage() {
  const [meta, setMeta] = useState<KbMeta | null>(null);
  const [docs, setDocs] = useState<KbDoc[]>([]);
  const [impacts, setImpacts] = useState<KbImpact[]>([]);
  const [queue, setQueue] = useState(0);
  const [view, setView] = useState<View>("Documents");
  const [openId, setOpenId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.kbDocuments().then(setDocs).catch((e: Error) => setError(e.message));
    api.kbImpacts().then(setImpacts).catch(() => undefined);
    api.kbReviewQueue().then((q) => setQueue(q.length)).catch(() => undefined);
  }, []);
  useEffect(() => { api.kbMeta().then(setMeta).catch((e: Error) => setError(e.message)); load(); }, [load]);

  if (!meta) return <main className="page">{error ? <div className="alert error">{error}</div> : <span className="muted">Loading…</span>}</main>;
  const counts: Partial<Record<View, number>> = { Advanced: queue + impacts.length };

  return (
    <main className="page">
      <header className="page-head">
        <span className="eyebrow">Grounding for the agents</span>
        <h1>Knowledge base</h1>
        <p className="muted">
          Policies, regulations, glossaries and templates the agents rely on. Add a document and, once approved, the
          agents use it. Remove it and they stop.
        </p>
      </header>
      {error && <div className="alert error">{error}</div>}

      <div className="tabs" role="tablist">
        {VIEWS.map((v) => (
          <button key={v} role="tab" aria-selected={view === v} className={view === v ? "active" : ""} onClick={() => setView(v)}>
            {v}{counts[v] ? <span className="count">{counts[v]}</span> : null}
          </button>
        ))}
      </div>

      {view === "Documents" && <Documents meta={meta} docs={docs} onOpen={setOpenId} onChanged={load} />}
      {view === "Ask" && <AskPanel />}
      {view === "Advanced" && (
        <div className="stack">
          <CollectionSummary meta={meta} docs={docs} />
          <h2>Review queue</h2>
          <ReviewQueue onChanged={load} />
          <h2>Removed documents still cited by projects</h2>
          <Impacts impacts={impacts} onResolved={load} />
          <Tester meta={meta} />
        </div>
      )}

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
const STATUS_LABEL: Record<string, string> = { active: "in use", draft: "waiting for approval" };

/** One list: search, add, approve and remove in place. */
function Documents({ meta, docs, onOpen, onChanged }: { meta: KbMeta; docs: KbDoc[]; onOpen: (id: number) => void; onChanged: () => void }) {
  const me = useMe().me;
  const [q, setQ] = useState("");
  const [collection, setCollection] = useState("");
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const colName = Object.fromEntries(meta.collections.map((c) => [c.id, c.name]));
  const approverRoles = (collectionId: string) => meta.collections.find((c) => c.id === collectionId)?.approver_roles ?? [];
  const roleFor = (collectionId: string) => approverRoles(collectionId).find((r) => me.roles.includes(r));

  const needle = q.trim().toLowerCase();
  const rows = docs
    .filter((d) => d.status === "active" || d.status === "draft")
    .filter((d) => (!collection || d.collection === collection) && (!needle || `${d.title} ${d.doc_key}`.toLowerCase().includes(needle)))
    .sort((a, b) => (a.status === b.status ? a.title.localeCompare(b.title) : a.status === "draft" ? -1 : 1));

  async function act(id: number, fn: () => Promise<unknown>) {
    setBusy(id); setError(null);
    try { await fn(); onChanged(); } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  }
  function approve(d: KbDoc) {
    const role = roleFor(d.collection);
    if (role) act(d.id, () => api.kbApprove(d.id, me.username, role));
  }
  function remove(d: KbDoc) {
    if (!window.confirm(`Remove "${d.title}" from the knowledge base? The agents will stop using it.`)) return;
    const reason = `Removed by ${me.username}`;
    act(d.id, () => (d.status === "draft" ? api.kbReject(d.id, me.username, reason) : api.kbWithdraw(d.id, me.username, reason)));
  }

  return (
    <section className="stack">
      <div className="row center-y">
        <input className="grow" aria-label="Search documents" placeholder="Search documents…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="Type" value={collection} onChange={(e) => setCollection(e.target.value)}>
          <option value="">All types</option>
          {meta.collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <button className="primary" onClick={() => setAdding(!adding)}>{adding ? "Cancel" : "+ Add document"}</button>
      </div>
      {adding && <QuickAdd meta={meta} onDone={() => { setAdding(false); onChanged(); }} />}
      {error && <div className="alert error">{error}</div>}
      {rows.length === 0 ? <div className="empty">No documents yet. Click “Add document” to upload one.</div> : (
        <div className="table-scroll">
          <table>
            <thead><tr><th>Document</th><th>Type</th><th>Status</th><th className="num">Actions</th></tr></thead>
            <tbody>
              {rows.map((d) => {
                const role = roleFor(d.collection);
                const canAct = Boolean(role) && busy !== d.id;
                const why = role ? undefined : `Only ${approverRoles(d.collection).join(" / ")} can approve or remove this type`;
                return (
                  <tr key={d.id}>
                    <td><button className="link" style={{ padding: 0, textAlign: "left", whiteSpace: "normal" }} onClick={() => onOpen(d.id)}>{d.title}</button>
                      <div className="muted small">added by {d.submitted_by}</div></td>
                    <td className="small">{colName[d.collection]}</td>
                    <td><span className={`tag ${STATUS_CLASS[d.status]}`}>{STATUS_LABEL[d.status] ?? d.status}</span></td>
                    <td className="num" style={{ whiteSpace: "nowrap" }}>
                      {d.status === "draft" && <><button className="primary" disabled={!canAct} title={why} onClick={() => approve(d)}>Approve</button>{" "}</>}
                      <button className="danger" disabled={!canAct} title={why} onClick={() => remove(d)}>Remove</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

const slug = (t: string) => t.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80);

/** Minimal add form: a file (or pasted text), a title, a type and a domain. Everything else gets a sensible default. */
function QuickAdd({ meta, onDone }: { meta: KbMeta; onDone: () => void }) {
  const me = useMe().me;
  const catalog = useCatalog();
  const [title, setTitle] = useState("");
  const [collection, setCollection] = useState("policy_control");
  const [domain, setDomain] = useState("all");
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [pasting, setPasting] = useState(false);
  const [sourceUrl, setSourceUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const role = meta.collections.find((c) => c.id === collection)?.approver_roles.find((r) => me.roles.includes(r));

  function pickFile(f: File | null) {
    setFile(f);
    if (f && !title) setTitle(f.name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " "));
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const url = sourceUrl.trim();
    let issuer = "Internal";
    if (url) {
      try { issuer = new URL(url).hostname; } catch { setError("The source link is not a valid URL."); return; }
    }
    const metadata = {
      // A unique key per upload: each document stands on its own, nothing is versioned or replaced.
      doc_key: `${slug(title) || "doc"}-${Date.now().toString(36)}`, collection, title: title.trim(), issuer,
      source_url: url || null, license: url ? "full_text" : "internal", jurisdictions: ["IN"], version: "1",
      effective_from: new Date().toISOString().slice(0, 10), applicability: { domains: [domain] },
    };
    const fd = new FormData();
    fd.append("metadata", JSON.stringify(metadata));
    fd.append("submitted_by", me.username);
    if (!pasting && file) fd.append("file", file); else fd.append("content", text);
    setBusy(true);
    try {
      const { document } = await api.kbSubmit(fd);
      if (role) await api.kbApprove(document.id, me.username, role);
      onDone();
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }

  return (
    <form className="card stack tight" onSubmit={submit}>
      <h2>Add a document</h2>
      {error && <div className="alert error">{error}</div>}
      <div className="segmented">
        <button type="button" className={!pasting ? "active" : ""} onClick={() => setPasting(false)}>Upload file</button>
        <button type="button" className={pasting ? "active" : ""} onClick={() => setPasting(true)}>Paste text</button>
      </div>
      {pasting ? <textarea rows={8} aria-label="Document text" value={text} onChange={(e) => setText(e.target.value)} />
        : <input type="file" aria-label="Document file" accept=".pdf,.docx,.md,.txt,.yaml,.yml" onChange={(e) => pickFile(e.target.files?.[0] ?? null)} />}
      <div className="row">
        <label className="grow" htmlFor="qa-title">Title<input id="qa-title" value={title} onChange={(e) => setTitle(e.target.value)} required minLength={3} /></label>
        <label className="grow" htmlFor="qa-col">Type
          <select id="qa-col" value={collection} onChange={(e) => setCollection(e.target.value)}>
            {meta.collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        <label className="grow" htmlFor="qa-dom">Domain
          <select id="qa-dom" value={domain} onChange={(e) => setDomain(e.target.value)}>
            <option value="all">All domains</option>
            {catalog.domains.filter((d) => d.status === "active").map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
      </div>
      <label htmlFor="qa-url">Source link <span className="muted small">(optional; needed only for official regulations and standards)</span>
        <input id="qa-url" value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder="https://…" /></label>
      <p className="note small">
        {role ? "You can approve this type, so the agents can use it straight away."
          : "It will wait for someone with the approver role before the agents use it."}
      </p>
      <div><button className="primary" type="submit" disabled={busy || title.trim().length < 3 || (pasting ? !text.trim() : !file)}>
        {busy ? "Adding…" : role ? "Add and approve" : "Add"}</button></div>
    </form>
  );
}

function DocumentPanel({ id, meta, onClose }: { id: number; meta: KbMeta; onClose: () => void; onChanged: () => void }) {
  const catalog = useCatalog();
  const [detail, setDetail] = useState<KbDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { api.kbDocument(id).then(setDetail).catch((e: Error) => setError(e.message)); }, [id]);
  if (!detail) return error ? <div className="alert error">{error}</div> : null;
  const d = detail.document;
  const col = meta.collections.find((c) => c.id === d.collection);
  const domains = d.applicability.domains[0] === "all" ? "All domains"
    : d.applicability.domains.map((x) => catalog.domain[x]?.name ?? x).join(", ");

  return (
    <div className="panel-backdrop" onClick={onClose}>
      <aside className="panel" role="dialog" aria-label={d.title} onClick={(e) => e.stopPropagation()}>
        <div className="section-head">
          <span className="eyebrow">{col?.name}</span>
          <button className="link" onClick={onClose}>Close</button>
        </div>
        <h2>{d.title}</h2>
        <div className="chips"><span className={`tag ${STATUS_CLASS[d.status]}`}>{STATUS_LABEL[d.status] ?? d.status}</span></div>

        <dl className="kv">
          <dt>Source</dt><dd>{d.source.issuer}{d.source.url && <> · <a href={d.source.url} target="_blank" rel="noreferrer">link</a></>}</dd>
          <dt>Jurisdiction</dt><dd>{d.jurisdictions.map((j) => meta.jurisdictions[j] ?? j).join(", ")}</dd>
          <dt>Effective from</dt><dd className="num">{d.effective_from}{d.effective_to && <> until {d.effective_to}</>}</dd>
          <dt>Domain</dt><dd>{domains}</dd>
        </dl>

        <section className="stack tight">
          <h3>Content</h3>
          <pre className="masked" style={{ whiteSpace: "pre-wrap", maxHeight: "60vh", overflow: "auto" }}>{detail.content}</pre>
        </section>
      </aside>
    </div>
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
