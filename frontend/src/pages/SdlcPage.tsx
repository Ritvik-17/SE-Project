import { useEffect, useState } from "react";
import { api, type SdlcCatalog } from "../api";

const SELECTION_STEPS: [string, string][] = [
  ["Measure the project", "Reads the approved baseline: how many requirements, how many integrations, how stable they are, how much is regulatory, which stakeholders took part, open questions and top risks."],
  ["Score the decision factors", "Each factor is scored 1–5. System size and stakeholder availability are measured from project data; the rest are estimated by the model from the requirements."],
  ["Answer the selection questions", "The course's questions about requirements, team, users and project risk are answered from measured data where possible, otherwise by the model. Approvers can correct any answer at the gate and re-rank."],
  ["Rank the models", "TOPSIS and a weighted fit against each model's ideal profile, plus how well the answers match, give every model a % suitability."],
  ["Apply the rules", "Sourced rules (problem statement, course slides, research, standards) add or subtract points when their conditions hold, for example strict regulation favours the V-Model."],
  ["Explain", "The model writes a plain-language explanation of the ranking, the alternatives and when to revisit. It cannot change the ranking."],
  ["People decide", "Project manager, architect, infosec and compliance approve the model or choose another with a justification."],
];

const COMPONENTS: [string, string][] = [
  ["Development phases", "The chosen model's own phases, in its order. Missing phases are added back and invented ones are dropped."],
  ["Activities", "Project-specific work in each phase, e.g. \"threat model the credit-bureau integration\"."],
  ["Responsible roles", "Who does the work, normalised to the system's stakeholder roles."],
  ["Deliverables", "What each phase must produce."],
  ["Security activities", "Security work per phase; mandatory controls are added where missing (see below)."],
  ["Testing requirements", "What must be tested in the phase, including transaction-integrity and audit-trail tests for financial systems."],
  ["Compliance checkpoints", "Regulatory evidence to collect and approvals needed, tied to the project's regulations."],
  ["Human-approval gates", "A named gate per phase with approver roles and pass criteria; the last release gate is the production-readiness go / no-go."],
  ["Entry and exit criteria", "When a phase may start and when it is done."],
  ["Traceability requirements", "Which trace links the phase creates or verifies (requirement → design → test → approval)."],
];

export default function SdlcPage() {
  const [cat, setCat] = useState<SdlcCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.sdlcCatalog().then(setCat).catch((e: Error) => setError(e.message)); }, []);

  return (
    <main className="page">
      <header className="page-head">
        <span className="eyebrow">Steps 13–15 · planning agent</span>
        <h1>SDLC engine</h1>
        <p className="muted">
          After the requirement baseline is approved, the planning agent recommends a software development life cycle
          (SDLC) model for the project and then customises that model into a project-specific workflow. People approve both
          under <em>Approve plan</em>.
        </p>
      </header>
      {error && <div className="alert error">{error}</div>}

      <section className="section">
        <h2>1. Choosing the model</h2>
        <ol className="stack tight">
          {SELECTION_STEPS.map(([t, d]) => <li key={t}><strong>{t}.</strong> <span className="muted">{d}</span></li>)}
        </ol>
      </section>

      <section className="section">
        <h2>2. Customising the chosen model</h2>
        <p className="muted small">For every phase of the approved model, the workflow sets out:</p>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Component</th><th>What the workflow contains</th></tr></thead>
            <tbody>{COMPONENTS.map(([c, d]) => <tr key={c}><td><strong>{c}</strong></td><td className="small">{d}</td></tr>)}</tbody>
          </table>
        </div>
        <p className="muted small">
          It also schedules a timeline from the model's structure (sequential, V-paired, sprints, cycles or a continuous
          pipeline) and draws a Gantt chart. Approvers can edit phases and the timeline; mandatory controls are put back if removed.
        </p>
      </section>

      {cat && (
        <>
          <section className="section">
            <h2>Mandatory controls for financial systems</h2>
            <p className="muted small">Added by fixed rules whenever the generated workflow leaves them out, so they never depend on the model.</p>
            <div className="table-scroll">
              <table>
                <thead><tr><th>Control</th><th>Phase</th><th>When</th></tr></thead>
                <tbody>{cat.mandatory_controls.map((c) => (
                  <tr key={c.control}><td>{c.control}</td><td className="small">{c.phase}</td><td className="small muted">{c.when}</td></tr>
                ))}</tbody>
              </table>
            </div>
          </section>

          <section className="section">
            <h2>The {cat.models.length} models</h2>
            <div className="stack">
              {cat.models.map((m) => (
                <details key={m.id} className="card">
                  <summary><strong>{m.name}</strong> <span className="tag">{m.structure.replace(/_/g, " ")}</span></summary>
                  <p className="small">{m.description}</p>
                  <p className="small muted">{m.cadence}</p>
                  <div className="chips">{m.phases.map((p) => (
                    <span key={p.name} className="chip" title={`${p.kinds.join(", ")} · ${p.recurrence.replace(/_/g, " ")}`}>{p.name}</span>
                  ))}</div>
                </details>
              ))}
            </div>
          </section>

          <div className="two-col">
            <section className="card">
              <h2>Decision factors ({cat.factors.length})</h2>
              <table>
                <thead><tr><th>Factor</th><th className="num">Weight</th></tr></thead>
                <tbody>{cat.factors.map((f) => <tr key={f.id}><td className="small">{f.name}</td><td className="num">{f.base_weight}</td></tr>)}</tbody>
              </table>
            </section>
            <section className="card">
              <h2>Selection questions ({cat.characteristics.reduce((n, g) => n + g.questions.length, 0)})</h2>
              {cat.characteristics.map((g) => (
                <details key={g.id}>
                  <summary>{g.name} ({g.questions.length})</summary>
                  <ul className="small">{g.questions.map((q) => <li key={q}>{q}</li>)}</ul>
                </details>
              ))}
            </section>
          </div>

          <section className="section">
            <details>
              <summary><strong>Selection rules ({cat.rules.length})</strong> <span className="muted small">· catalog version {cat.version}</span></summary>
              <div className="table-scroll">
                <table>
                  <thead><tr><th>Rule</th><th>Reason</th><th>Effect</th><th>Source</th></tr></thead>
                  <tbody>{cat.rules.map((r) => (
                    <tr key={r.id}>
                      <td><code>{r.id}</code></td>
                      <td className="small">{r.reason}</td>
                      <td className="small num">{Object.entries(r.effects).map(([m, pts]) => `${m.replace(/_/g, " ")} ${pts > 0 ? "+" : ""}${pts}`).join(", ")}</td>
                      <td className="small muted">{r.source}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            </details>
          </section>
        </>
      )}
    </main>
  );
}
