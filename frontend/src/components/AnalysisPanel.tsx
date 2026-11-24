import { useEffect, useState } from "react";
import { api, type Decision, type Project, type RunStatus } from "../api";
import ArtifactsView from "./ArtifactsView";
import BaselineGateView from "./gates/BaselineGate";
import ClarificationGateView from "./gates/ClarificationGate";
import SdlcGateView from "./gates/SdlcGate";
import WorkflowGateView from "./gates/WorkflowGate";

interface Props { project: Project; sourceCount: number }

const STAGES = [
  { key: "analysis", label: "Agents analyse" },
  { key: "clarification", label: "Clarification" },
  { key: "baseline", label: "Baseline approval" },
  { key: "sdlc", label: "SDLC approval" },
  { key: "workflow", label: "Workflow approval" },
  { key: "completed", label: "Documents" },
];

export default function AnalysisPanel({ project, sourceCount }: Props) {
  const [run, setRun] = useState<RunStatus | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.run(project.id).then(setRun).catch((e: Error) => setError(e.message));
  }, [project.id]);

  async function act(label: string, fn: () => Promise<RunStatus>) {
    setBusy(label);
    setError(null);
    try {
      setRun(await fn());
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const decide = (label: string, d: Decision) => act(label, () => api.decide(project.id, d));
  if (!run) return <p className="muted">Loading…</p>;

  const stage = run.status === "completed" ? "completed" : run.gate ?? (run.status === "not_started" ? "" : "analysis");
  const stageIndex = STAGES.findIndex((s) => s.key === stage);

  return (
    <div className="stack">
      <section className="card">
        <div className="row between">
          <div>
            <h2>Agent workflow</h2>
            <p className="muted small">
              {sourceCount} source(s) · pass {run.state.iteration ?? 0} · clarification rounds {run.state.clarification_round ?? 0}
              {run.state.quality && <> · quality <strong>{Math.round(run.state.quality.overall * 100)}%</strong></>}
            </p>
          </div>
          <button className="primary" disabled={!!busy || sourceCount === 0}
            onClick={() => act("Running the agents: extraction, classification, five parallel analysts, then validation. This takes a minute…",
              () => api.startRun(project.id))}>
            {run.status === "not_started" ? "Run analysis" : "Restart analysis"}
          </button>
        </div>
        <ol className="track">
          {STAGES.map((s, i) => (
            <li key={s.key} className={i < stageIndex ? "done" : i === stageIndex ? "current" : ""}>{s.label}</li>
          ))}
        </ol>
      </section>

      {busy && <div className="alert info" role="status"><span className="spinner" />{busy}</div>}
      {error && <div className="alert error">{error}</div>}

      {run.pending?.gate === "clarification" && <ClarificationGateView gate={run.pending} busy={!!busy} onDecide={decide} />}
      {run.pending?.gate === "baseline" && <BaselineGateView gate={run.pending} busy={!!busy} onDecide={decide} />}
      {run.pending?.gate === "sdlc" && <SdlcGateView gate={run.pending} busy={!!busy} onDecide={decide} />}
      {run.pending?.gate === "workflow" && <WorkflowGateView gate={run.pending} busy={!!busy} onDecide={decide} />}
      {run.status === "completed" && project.status === "artifacts_stale" && (
        <div className="alert warn">An approved change altered the baseline. Regenerate the documents from the Governance tab.</div>
      )}
      {run.status === "completed" && <ArtifactsView projectId={project.id} />}
    </div>
  );
}
