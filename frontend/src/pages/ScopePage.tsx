import { useCatalog } from "../catalog";

/** Steps 1–3 made visible: domains, outputs, stakeholder × category mapping and input sources. */
export default function ScopePage() {
  const c = useCatalog();

  return (
    <main className="page">
      <header className="page-head">
        <span className="eyebrow">Steps 1–3 · scope, stakeholders, inputs</span>
        <h1>System scope</h1>
        <p className="muted">
          Which domains the system supports, which stakeholders supply which requirements, and which inputs it accepts.
          Everything here is read from the catalog in <code>app/catalog/data</code>.
        </p>
      </header>

      <section className="section">
        <h2>Role × requirement category</h2>
        <p className="muted small">● main authority for the category · ○ contributes</p>
        <div className="table-scroll">
          <table className="matrix">
            <thead>
              <tr>
                <th>Role</th>
                {c.categories.map((cat) => (
                  <th key={cat.id} title={cat.description}><span className="vertical">{cat.name.replace(" requirements", "")}</span></th>
                ))}
              </tr>
            </thead>
            <tbody>
              {c.roles.map((r) => (
                <tr key={r.id}>
                  <th title={r.provides}>{r.name}</th>
                  {c.categories.map((cat) => (
                    <td key={cat.id} className="center">
                      {r.categories.primary.includes(cat.id) ? "●" : r.categories.secondary.includes(cat.id) ? "○" : ""}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="section">
        <h2>Supported domains</h2>
        <table>
          <thead><tr><th>Domain</th><th>Mandatory categories</th><th>Typical regulations</th></tr></thead>
          <tbody>
            {c.domains.map((d) => (
              <tr key={d.id}>
                <td><strong>{d.name}</strong> <span className="tag">{d.code}</span> <span className={`tag ${d.status === "active" ? "ok" : ""}`}>{d.status}</span><div className="muted small">{d.description}</div></td>
                <td>{d.mandatory_categories.map((x) => <span key={x} className="chip">{x}</span>)}</td>
                <td className="small">{d.typical_regulations.join("; ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted small">Regulations are starting points. A compliance officer must confirm which ones apply.</p>
      </section>

      <section className="section">
        <h2>Input sources</h2>
        <table>
          <thead><tr><th>Source</th><th>Type</th><th>Default sensitivity</th><th>Formats</th><th>Typical roles</th></tr></thead>
          <tbody>
            {c.sources.map((s) => (
              <tr key={s.id}>
                <td><strong>{s.name}</strong><div className="muted small">{s.extraction_guidance}</div></td>
                <td>{s.structured ? "Structured" : "Unstructured"}</td>
                <td><span className={`badge sens-${s.default_sensitivity}`}>{s.default_sensitivity}</span></td>
                <td className="small">{s.formats.join(", ")}</td>
                <td className="small">{s.typical_roles.map((r) => c.role[r].name).join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="section">
        <h2>Expected outputs</h2>
        <table>
          <thead><tr><th>Output</th><th>Produced by</th><th>Status</th></tr></thead>
          <tbody>
            {c.outputs.map((o) => (
              <tr key={o.id}>
                <td><strong>{o.name}</strong><div className="muted small">{o.description}</div></td>
                <td><code>{o.produced_by}</code></td>
                <td><span className={`tag ${o.status === "implemented" ? "ok" : ""}`}>{o.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}
