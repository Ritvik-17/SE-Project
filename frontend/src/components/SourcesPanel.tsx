import { Fragment, useState, type FormEvent } from "react";
import { api, type Project, type Source } from "../api";
import { useCatalog } from "../catalog";

interface Props { project: Project; sources: Source[]; onChange: () => void }

export default function SourcesPanel({ project, sources, onChange }: Props) {
  const catalog = useCatalog();
  const domain = catalog.domain[project.domain];
  const [sourceType, setSourceType] = useState(catalog.sources[0].id);
  const [role, setRole] = useState("");
  const [title, setTitle] = useState("");
  const [mode, setMode] = useState<"text" | "file">("text");
  const [content, setContent] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Source | null>(null);

  const type = catalog.source[sourceType];
  const coveredRoles = new Set(sources.map((s) => s.stakeholder_role).filter(Boolean));

  async function submit(e: FormEvent) {
    e.preventDefault();
    const form = new FormData();
    form.append("source_type", sourceType);
    form.append("title", title.trim() || type.name);
    if (role) form.append("stakeholder_role", role);
    if (mode === "file" && file) form.append("file", file);
    else form.append("content", content);
    setBusy(true);
    setError(null);
    try {
      await api.addSource(project.id, form);
      setTitle(""); setContent(""); setFile(null);
      onChange();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function toggle(s: Source) {
    setExpanded(expanded?.id === s.id ? null : await api.source(project.id, s.id));
  }

  async function remove(s: Source) {
    if (!confirm(`Delete source "${s.title}"?`)) return;
    await api.deleteSource(project.id, s.id);
    if (expanded?.id === s.id) setExpanded(null);
    onChange();
  }

  return (
    <div className="stack">
      <section className="section">
        <h2>Stakeholder coverage</h2>
        <p className="muted small">Roles whose input is expected for {domain.name}. Missing roles are flagged during validation.</p>
        <div className="chips">
          {domain.required_roles.map((r) => (
            <span key={r} className={`chip ${coveredRoles.has(r) ? "ok" : "missing"}`}>
              {catalog.role[r].name}{coveredRoles.has(r) ? "" : " · missing"}
            </span>
          ))}
        </div>
      </section>

      <section className="card">
        <h2>Add input source</h2>
        {error && <div className="alert error">{error}</div>}
        <form onSubmit={submit} className="stack">
          <div className="row">
            <label className="grow">
              Source type
              <select value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
                {catalog.sources.map((s) => (
                  <option key={s.id} value={s.id}>{s.name} ({s.structured ? "structured" : "unstructured"})</option>
                ))}
              </select>
            </label>
            <label className="grow">
              Stakeholder role
              <select value={role} onChange={(e) => setRole(e.target.value)}>
                <option value="">— Not from a specific stakeholder —</option>
                {catalog.roles.map((r) => (
                  <option key={r.id} value={r.id}>{r.name}{type.typical_roles.includes(r.id) ? " (typical)" : ""}</option>
                ))}
              </select>
            </label>
          </div>
          <p className="muted small">{type.extraction_guidance} Accepted files: {type.formats.join(", ")}.</p>
          <label>
            Title
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={type.name} />
          </label>
          <div className="segmented">
            <button type="button" className={mode === "text" ? "active" : ""} onClick={() => setMode("text")}>Paste text</button>
            <button type="button" className={mode === "file" ? "active" : ""} onClick={() => setMode("file")}>Upload file</button>
          </div>
          {mode === "text" ? (
            <textarea rows={8} value={content} onChange={(e) => setContent(e.target.value)}
              placeholder="Paste the conversation, notes, email or document text…" />
          ) : (
            <input type="file" accept={type.formats.map((f) => `.${f}`).join(",")}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          )}
          <p className="note">
            Names, contact details, card, account and ID numbers are masked before anything is stored. Only the masked text is saved or sent to the model.
          </p>
          <div>
            <button type="submit" className="primary" disabled={busy || (mode === "text" ? !content.trim() : !file)}>
              {busy ? "Masking & classifying…" : "Add source"}
            </button>
          </div>
        </form>
      </section>

      <section className="section">
        <h2>Sources ({sources.length})</h2>
        {sources.length === 0 ? <div className="empty">No input yet. Paste a conversation, upload a document, or run an interview.</div> : (
          <table>
            <thead>
              <tr><th>Title</th><th>Type</th><th>Role</th><th>Sensitivity</th><th>Masked</th><th /></tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <Fragment key={s.id}>
                  <tr>
                    <td>
                      <strong>{s.title}</strong>
                      {s.filename && <div className="muted small">{s.filename}</div>}
                      {s.injection_flags.length > 0 && (
                        <div className="alert warn">Contains instruction-like text the agents will ignore: {s.injection_flags.join("; ")}</div>
                      )}
                    </td>
                    <td className="small">{catalog.source[s.source_type]?.name}</td>
                    <td className="small">{s.stakeholder_role ? catalog.role[s.stakeholder_role]?.name : "—"}</td>
                    <td><span className={`badge sens-${s.sensitivity}`}>{s.sensitivity}</span></td>
                    <td className="small">
                      {Object.keys(s.redactions).length === 0 ? "none" :
                        Object.entries(s.redactions).map(([k, v]) => <span key={k} className="chip">{k} ×{v}</span>)}
                      <div className="muted">{s.masking_engine}</div>
                    </td>
                    <td className="nowrap">
                      <button className="link" onClick={() => toggle(s)}>{expanded?.id === s.id ? "Hide" : "View"}</button>
                      <button className="link danger" onClick={() => remove(s)}>Delete</button>
                    </td>
                  </tr>
                  {expanded?.id === s.id && (
                    <tr>
                      <td colSpan={6}>
                        <p className="muted small">Masked text as the agents see it · SHA-256 {s.content_sha256.slice(0, 16)}…</p>
                        <pre className="masked">{expanded.masked_text}</pre>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
