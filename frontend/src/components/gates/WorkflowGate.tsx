import { useState } from "react";
import type { Decision, WorkflowEdit, WorkflowGate } from "../../api";
import WorkflowView from "../WorkflowView";
import ApproverBar from "./ApproverBar";

interface Props { gate: WorkflowGate; busy: boolean; onDecide: (label: string, d: Decision) => void }

const LIST_FIELDS = ["activities", "deliverables", "security_activities", "testing", "compliance_checkpoints",
  "entry_criteria", "exit_criteria", "traceability"] as const;

/** Step 15 output under human control (step 16): approve, modify phases and timeline, or regenerate. */
export default function WorkflowGateView({ gate, busy, onDecide }: Props) {
  const wf = gate.workflow;
  const [editing, setEditing] = useState(false);
  const [edits, setEdits] = useState<Record<string, WorkflowEdit>>({});
  const [schedule, setSchedule] = useState<Record<string, number>>({});
  const scheduleKeys = (["iterations", "iteration_length_weeks", "iterations_per_release", "cycles"] as const)
    .filter((k) => wf.schedule?.[k] !== undefined);

  const set = (phase: string, field: string, value: WorkflowEdit["value"]) =>
    setEdits({ ...edits, [`${phase}|${field}`]: { phase, field, value } });
  const editList = Object.values(edits);
  const changed = editList.length + Object.keys(schedule).length;

  const decide = (decision: "approve" | "regenerate") => (reviewer: string, role: string, feedback: string) => {
    onDecide(decision === "approve" ? (changed ? "Applying your changes and recording approval…" : "Recording approval…")
      : "Regenerating the workflow with your feedback…",
      { gate: "workflow", decision, reviewer, reviewer_role: role, feedback,
        edits: decision === "approve" ? editList : [], schedule: decision === "approve" ? schedule : {} });
    setEdits({}); setSchedule({}); setEditing(false);
  };

  return (
    <div className="stack">
      <section className="card">
        <div className="section-head">
          <h2>Project workflow: approval</h2>
          <button onClick={() => setEditing(!editing)}>{editing ? "Hide editor" : "Modify workflow"}</button>
        </div>
        <p className="muted small">
          The {wf.model} model was customised for this project. Approve it, change phases and timeline, or ask for regeneration
          with feedback. Mandatory security and compliance controls are re-added if an edit removes them.
        </p>
      </section>

      {editing && (
        <section className="card stack">
          {scheduleKeys.length > 0 && (
            <div className="row">
              {scheduleKeys.map((k) => (
                <label key={k} className="grow">{k.replace(/_/g, " ")}
                  <input type="number" min={k === "iterations_per_release" ? 0 : 1} step={k === "iteration_length_weeks" ? 0.5 : 1}
                    value={schedule[k] ?? wf.schedule?.[k] ?? ""} onChange={(e) => setSchedule({ ...schedule, [k]: Number(e.target.value) })} />
                </label>
              ))}
            </div>
          )}
          {wf.phases.map((p) => (
            <details key={p.name} className="edit-phase">
              <summary><strong>{p.name}</strong> <span className="muted small">{p.timing}</span></summary>
              <div className="stack">
                <label>Weeks per occurrence
                  <input type="number" min={0.2} step={0.5} value={(edits[`${p.name}|duration_weeks`]?.value as number) ?? p.duration_weeks ?? 1}
                    onChange={(e) => set(p.name, "duration_weeks", Number(e.target.value))} />
                </label>
                {LIST_FIELDS.map((f) => (
                  <label key={f}>{f.replace(/_/g, " ")} <span className="muted small">(one per line)</span>
                    <textarea rows={3} value={((edits[`${p.name}|${f}`]?.value as string[]) ?? p[f] ?? []).join("\n")}
                      onChange={(e) => set(p.name, f, e.target.value.split("\n"))} />
                  </label>
                ))}
              </div>
            </details>
          ))}
          {changed > 0 && <div className="alert info">{changed} change(s) will be applied when you approve.</div>}
        </section>
      )}

      <WorkflowView workflow={wf} />
      <ApproverBar required={gate.required_approvers} pending={gate.pending_approvers} approvals={gate.approvals} busy={busy}
        approveLabel={changed ? "Apply changes and approve" : "Approve workflow"} onApprove={decide("approve")} onRegenerate={decide("regenerate")} />
    </div>
  );
}
