import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type KbImpact, type Project, type Source } from "../api";
import { useCatalog } from "../catalog";
import AnalysisPanel from "../components/AnalysisPanel";
import AuditPanel from "../components/AuditPanel";
import GovernancePanel from "../components/GovernancePanel";
import InterviewPanel from "../components/InterviewPanel";
import RecordsPanel from "../components/RecordsPanel";
import SourcesPanel from "../components/SourcesPanel";

const TABS = ["Inputs", "Interviews", "Analysis & approvals", "Governance", "Evaluation & records", "Audit trail"] as const;
type Tab = (typeof TABS)[number];

export default function ProjectPage() {
  const pid = Number(useParams().id);
  const catalog = useCatalog();
  const [project, setProject] = useState<Project | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [tab, setTab] = useState<Tab>("Inputs");
  const [error, setError] = useState<string | null>(null);
  const [impacts, setImpacts] = useState<KbImpact[]>([]);

  const refreshSources = useCallback(() => {
    api.sources(pid).then(setSources).catch((e: Error) => setError(e.message));
  }, [pid]);

  const refreshProject = useCallback(() => {
    api.project(pid).then(setProject).catch((e: Error) => setError(e.message));
  }, [pid]);

  useEffect(() => {
    api.project(pid).then((p) => { setProject(p); if (p.status !== "created") setTab("Analysis & approvals"); })
      .catch((e: Error) => setError(e.message));
    refreshSources();
    api.kbImpacts(pid).then(setImpacts).catch(() => undefined);
  }, [pid, refreshSources]);

  if (error) return <main className="page"><div className="alert error">{error}</div></main>;
  if (!project) return <main className="page muted">Loading…</main>;
  const domain = catalog.domain[project.domain];

  return (
    <main className="page">
      <header className="page-head">
        <span className="eyebrow"><Link to="/">Projects</Link> / {domain.code}</span>
        <h1>{project.name}</h1>
        <p className="muted">{domain.name} · jurisdiction {project.jurisdiction} · {sources.length} input source{sources.length === 1 ? "" : "s"}</p>
      </header>
      {project.deployment_stage === "advisory" && (
        <div className="alert warn">
          <strong>Advisory mode.</strong> The assistant is running alongside the business analysts. Its documents are marked advisory and are
          not official; compare them with the analysts' work under <em>Evaluation &amp; records</em>. Decisions remain with the approvers.
        </div>
      )}
      {impacts.map((i) => (
        <div key={i.id} className="alert warn">
          Regulatory change: this project cites <code>{i.doc_key}</code> v{i.old_version}, which was {i.change}
          {i.new_version && <> by v{i.new_version}</>}. Re-run the analysis to re-evaluate compliance.
        </div>
      ))}

      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
            {t}{t === "Inputs" && <span className="count">{sources.length}</span>}
          </button>
        ))}
      </div>

      {tab === "Inputs" && <SourcesPanel project={project} sources={sources} onChange={refreshSources} />}
      {tab === "Interviews" && (
        <InterviewPanel project={project} onSubmitted={() => { refreshSources(); setTab("Inputs"); }} onSourcesChanged={refreshSources} />
      )}
      {tab === "Analysis & approvals" && <AnalysisPanel project={project} sourceCount={sources.length} />}
      {tab === "Governance" && <GovernancePanel project={project} onProjectChanged={refreshProject} />}
      {tab === "Evaluation & records" && <RecordsPanel project={project} />}
      {tab === "Audit trail" && <AuditPanel projectId={pid} />}
    </main>
  );
}
