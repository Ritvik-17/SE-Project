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
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"list" | "new">("list");

  useEffect(() => {
    api.projects().then((ps) => { setProjects(ps); if (ps.length === 0) setTab("new"); }).catch((e: Error) => setError(e.message));
  }, []);

  async function create(e: FormEvent) {
    e.preventDefault();
    try {
      const p = await api.createProject(name.trim(), domain);
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

      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === "list"} className={tab === "list" ? "active" : ""} onClick={() => setTab("list")}>
          Your projects{projects ? <span className="count">{projects.length}</span> : null}
        </button>
        <button role="tab" aria-selected={tab === "new"} className={tab === "new" ? "active" : ""} onClick={() => setTab("new")}>
          New project
        </button>
      </div>

      {tab === "list" && projects && projects.length === 0 && (
        <div className="empty">No projects yet. <button className="link" onClick={() => setTab("new")}>Start a new project</button>.</div>
      )}
      {tab === "list" && projects && projects.length > 0 && (
        <section className="section">
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

      {tab === "new" && <form className="card" onSubmit={create}>
        <h2>Start a project</h2>
        <label htmlFor="project-name">
          Project name
          <input id="project-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Personal loan origination portal" required />
        </label>
        <fieldset>
          <legend>Project type</legend>
          <div className="domain-grid">
            {catalog.domains.filter((d) => d.status === "active").map((d) => (
              <label key={d.id} className={`domain-option ${domain === d.id ? "selected" : ""}`}>
                <input type="radio" name="domain" value={d.id} checked={domain === d.id} onChange={() => setDomain(d.id)} />
                <span className="domain-code">{d.code}</span>
                <strong>{d.name}</strong>
                <span className="muted small">{d.description}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <div className="note">
          <strong>Information to collect next.</strong> After you create the project you add its inputs (interview notes,
          e-mails, policies, specifications, API files) on the <em>Inputs</em> tab, each tagged with the stakeholder it came from.
        </div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Stakeholder</th><th>Typically provides</th></tr></thead>
            <tbody>{selected.required_roles.map((r) => (
              <tr key={r}><td><strong>{catalog.role[r].name}</strong></td><td className="small muted">{catalog.role[r].provides}</td></tr>
            ))}</tbody>
          </table>
        </div>
        <p className="small muted">The approved baseline must cover these requirement categories: {selected.mandatory_categories.join(", ")}.</p>
        <div><button type="submit" className="primary" disabled={!name.trim()}>Create project and add inputs</button></div>
      </form>}
    </main>
  );
}
