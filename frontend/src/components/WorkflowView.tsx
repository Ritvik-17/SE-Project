import type { SdlcWorkflow } from "../api";
import { useCatalog } from "../catalog";
import Diagram from "./Diagram";

function List({ items, added }: { items: string[]; added: Set<string> }) {
  if (items.length === 0) return <>—</>;
  return (
    <ul>
      {items.map((x) => <li key={x} className={added.has(x) ? "added" : ""}>{x}{added.has(x) && " (added by control rule)"}</li>)}
    </ul>
  );
}

const RECURRENCE: Record<string, string> = {
  once: "once", per_iteration: "every iteration", per_release: "every release", per_cycle: "every cycle", continuous: "continuous",
};

/** Project-specific SDLC workflow (problem statement step 15): timeline, how each component runs, phases with gates. */
export default function WorkflowView({ workflow }: { workflow: SdlcWorkflow }) {
  const catalog = useCatalog();
  if (!workflow?.phases?.length) return <div className="empty">No workflow generated.</div>;
  const added = new Set(workflow.controls_added_by_rules.map((c) => c.control));
  const role = (r: string) => catalog.role[r]?.name ?? r;
  const s = workflow.schedule;

  return (
    <div className="stack">
      <div className="card">
        <div className="section-head">
          <h2>{workflow.model} workflow for this project</h2>
          <span className="muted small num">
            {workflow.phases.length} phases{s && <> · {s.total_weeks} weeks from {s.start_date}</>} · {workflow.controls_added_by_rules.length} mandatory controls added
          </span>
        </div>
        <p><strong>How it runs:</strong> {workflow.cadence}</p>
        {s && (s.iterations || s.cycles) && (
          <p className="small muted">
            {s.cycles ? `${s.cycles} cycles` : `${s.iterations} iterations of ${s.iteration_length_weeks} weeks`}
            {s.iterations_per_release ? `, a release every ${s.iterations_per_release} iteration(s)` : ""}
          </p>
        )}
        {workflow.gantt && <Diagram code={workflow.gantt} />}
        {(workflow.phases_dropped?.length ?? 0) > 0 && (
          <p className="note">Not part of {workflow.model}, so left out: {workflow.phases_dropped!.join(", ")}.</p>
        )}
        {(workflow.phases_added_by_rules?.length ?? 0) > 0 && (
          <div className="alert warn">Canonical phases the generator skipped, added back: {workflow.phases_added_by_rules!.join(", ")}</div>
        )}
        {workflow.requirements_not_assigned.length > 0 && (
          <div className="alert warn">Not assigned to any phase: {workflow.requirements_not_assigned.join(", ")}</div>
        )}
      </div>

      {workflow.component_plan && workflow.component_plan.length > 0 && (
        <section className="card">
          <h3>How each component runs</h3>
          <div className="table-scroll">
            <table>
              <thead><tr><th>Component</th><th>In this project</th><th>{workflow.model} norm</th></tr></thead>
              <tbody>{workflow.component_plan.map((c) => (
                <tr key={c.component}>
                  <td><strong>{c.component[0].toUpperCase() + c.component.slice(1)}</strong></td>
                  <td className="small">{c.how}{c.source === "model default" && <span className="muted"> (model default)</span>}</td>
                  <td className="small muted">{c.model_norm}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          {workflow.controls_added_by_rules.length > 0 && (
            <p className="note">
              Highlighted items below were added by the financial-sector control rules in the phase they belong to: threat
              modelling in design, static security testing in implementation, transaction-integrity testing in validation,
              compliance approval before deployment.
            </p>
          )}
        </section>
      )}

      <ol className="phases">
        {workflow.phases.map((p) => (
          <li key={p.name} className="phase">
            <div className="phase-body">
              <div className="section-head">
                <h3>{p.name}</h3>
                <span className="small muted">{p.timing}{p.recurrence && p.recurrence !== "once" && ` · ${RECURRENCE[p.recurrence]}`}</span>
              </div>
              <p className="small">{p.objective}</p>
              <p className="small muted">
                Roles: {p.responsible_roles.map(role).join(", ")}
                {p.kinds && <> · does: {p.kinds.join(", ")}</>}
                {p.duration_weeks !== undefined && <> · {p.duration_weeks} week(s) per occurrence</>}
                {p.pairs_with && <> · its tests run in {p.pairs_with}</>}
                {p.designed_in && <> · tests designed in {p.designed_in}</>}
              </p>
              <dl className="phase-grid">
                <div><dt>Activities</dt><dd><List items={p.activities} added={added} /></dd></div>
                <div><dt>Deliverables</dt><dd><List items={p.deliverables} added={added} /></dd></div>
                <div><dt>Security</dt><dd><List items={p.security_activities} added={added} /></dd></div>
                <div><dt>Testing</dt><dd><List items={p.testing} added={added} /></dd></div>
                <div><dt>Compliance checkpoints</dt><dd><List items={p.compliance_checkpoints} added={added} /></dd></div>
                <div><dt>Entry / exit</dt><dd><List items={[...p.entry_criteria.map((x) => `In: ${x}`), ...p.exit_criteria.map((x) => `Out: ${x}`)]} added={added} /></dd></div>
                <div><dt>Traceability</dt><dd><List items={p.traceability ?? []} added={added} /></dd></div>
              </dl>
              <div className="gate">
                <strong>Human approval gate: {p.approval_gate.name}</strong> · {p.approval_gate.approvers.map(role).join(", ")}
                {p.approval_gate.hitl_control === "production_readiness" && <span className="tag accent" style={{ marginLeft: 6 }}>production readiness</span>}
                <div className="muted">{p.approval_gate.criteria.join("; ")}</div>
              </div>
              {p.requirement_ids.length > 0 && (
                <div className="small">Delivers: {p.requirement_ids.map((x) => <code key={x} style={{ marginRight: 6 }}>{x}</code>)}</div>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
