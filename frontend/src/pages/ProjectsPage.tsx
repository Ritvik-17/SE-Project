import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Project } from "../api";
import { useCatalog } from "../catalog";

const STATUS_LABEL: Record<string, string> = {
  created: "Collecting input", analysing: "Under analysis", baselined: "Baseline approved", completed: "Documents ready",
};

export default function ProjectsPage() {
  const catalog = useCatalog();
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("loan_processing");
  const [jurisdiction, setJurisdiction] = useState("IN");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.projects().then(setProjects).catch((e: Error) => setError(e.message));
  }, []);

  async function create(e: FormEvent) {
    e.preventDefault();
    try {
      const p = await api.createProject(name.trim(), domain, jurisdiction);
      navigate(`/projects/${p.id}`);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const selected = catalog.domain[domain];

  return (
    <main className="page">
      <header className="page-head">
        <span className="eyebrow">Requirements engineering for financial services</span>
        <h1>Projects</h1>
        <p className="muted">
          Each project collects stakeholder input, runs the agents, and moves through clarification and approval
          to a baselined set of requirements and an approved SDLC.
        </p>
      </header>
      {error && <div className="alert error">{error}</div>}

      {projects && projects.length > 0 && (
        <section className="section">
          <h2>Your projects</h2>
          <div className="table-scroll">
            <table>
              <thead><tr><th>Project</th><th>Domain</th><th>Stage</th><th className="num">#</th></tr></thead>
              <tbody>
                {projects.map((p) => (
                  <tr key={p.id}>
                    <td><Link to={`/projects/${p.id}`}><strong>{p.name}</strong></Link></td>
                    <td><span className="domain-code">{catalog.domain[p.domain]?.code}</span> {catalog.domain[p.domain]?.name ?? p.domain}</td>
                    <td><span className={`tag ${p.status === "completed" ? "ok" : p.status === "baselined" ? "accent" : ""}`}>
                      {STATUS_LABEL[p.status] ?? p.status.replace(/_/g, " ")}</span></td>
                    <td className="num muted">{p.id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <form className="card" onSubmit={create}>
        <h2>Start a project</h2>
        <label htmlFor="project-name">
          Project name
          <input id="project-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Personal loan origination portal" required />
        </label>
        <fieldset>
          <legend>Financial domain</legend>
          <div className="domain-grid">
            {catalog.domains.map((d) => (
              <label key={d.id} className={`domain-option ${domain === d.id ? "selected" : ""} ${d.status === "planned" ? "planned" : ""}`}>
                <input type="radio" name="domain" value={d.id} checked={domain === d.id} disabled={d.status === "planned"}
                  onChange={() => setDomain(d.id)} />
                <span className="domain-code">{d.code}{d.status === "planned" && <span className="tag" style={{ marginLeft: 6 }}>planned</span>}</span>
                <strong>{d.name}</strong>
                <span className="muted small">{d.description}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <label htmlFor="project-jur" style={{ maxWidth: 320 }}>
          Jurisdiction
          <select id="project-jur" value={jurisdiction} onChange={(e) => setJurisdiction(e.target.value)}>
            <option value="IN">India</option><option value="EU">European Union</option><option value="UK">United Kingdom</option>
            <option value="US">United States</option><option value="GLOBAL">Global / international</option>
          </select>
        </label>
        <div className="note">
          Only regulations for this jurisdiction (and international ones) are retrieved for compliance analysis.
          Two domains are active now; the others are planned and will be enabled later.
        </div>
        <div className="note">
          <strong>{selected.name}</strong> needs input from {selected.required_roles.map((r) => catalog.role[r].name).join(", ")}.
          The baseline must cover {selected.mandatory_categories.join(", ")} requirements.
        </div>
        <div><button type="submit" className="primary" disabled={!name.trim()}>Create project</button></div>
      </form>
    </main>
  );
}
