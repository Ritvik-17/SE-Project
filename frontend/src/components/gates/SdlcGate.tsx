import { useMemo, useState } from "react";
import type { Answer, Decision, SdlcCharacteristic, SdlcGate } from "../../api";
import { useCatalog } from "../../catalog";
import ApproverBar from "./ApproverBar";

interface Props { gate: SdlcGate; busy: boolean; onDecide: (label: string, d: Decision) => void }

export function Pips({ value }: { value: number }) {
  return <span className="pips" aria-label={`${value} of 5`}>{[1, 2, 3, 4, 5].map((n) => <i key={n} className={n <= value ? "on" : ""} />)}</span>;
}

const SOURCE_LABEL: Record<string, string> = { human: "approver", derived: "measured", llm: "AI", unknown: "unknown" };

export default function SdlcGateView({ gate, busy, onDecide }: Props) {
  const [selected, setSelected] = useState(gate.selected_model ?? gate.recommendations[0].model);
  const factors = Object.entries(gate.factors).filter(([, v]) => typeof v === "number") as [string, number][];
  const sources = (gate.factors.factor_sources ?? {}) as Record<string, string>;
  const ex = gate.explanation;

  const decide = (decision: "approve" | "regenerate") => (reviewer: string, role: string, feedback: string) =>
    onDecide(decision === "approve" ? "Recording SDLC approval…" : "Re-assessing the project with your feedback…",
      { gate: "sdlc", decision, reviewer, reviewer_role: role, feedback, selected_model: decision === "approve" ? selected : null });

  return (
    <div className="stack">
      <section className="card">
        <div className="section-head">
          <h2>SDLC recommendation</h2>
          <span className="muted small">Suitability from TOPSIS + weighted fit (factors and course characteristics), ± sourced rules{gate.rules_version && <> · rules {gate.rules_version}</>}</span>
        </div>
        {ex?.summary && <p>{ex.summary}</p>}
        <div role="radiogroup" aria-label="SDLC model">
          {gate.recommendations.map((s, i) => (
            <label key={s.model} className={`rank ${selected === s.model ? "selected" : ""}`}>
              <input type="radio" name="sdlc" checked={selected === s.model} onChange={() => setSelected(s.model)} />
              <span><span className="rank-name">{s.model}</span>{i === 0 && <span className="tag accent" style={{ marginLeft: 6 }}>recommended</span>}</span>
              <div className="bar" title={`TOPSIS ${s.topsis} · fit ${s.fit}`}><div className="bar-fill" style={{ width: `${s.score}%` }} /></div>
              <span className="bar-value">{s.score}%</span>
              <span className="rank-detail">
                <span className="mono" title="TOPSIS closeness · weighted fit · course characteristics matched">
                  T{s.topsis} F{s.fit}{s.characteristics_fit != null && <> C{s.characteristics_fit}</>}
                </span>
                {s.rule_adjustments.map((a) => (
                  <span key={a.rule} className={`tag ${a.points > 0 ? "ok" : "sev-high"}`} title={`${a.reason}${a.source ? ` (${a.source})` : ""}`} style={{ marginLeft: 6 }}>
                    {a.rule} {a.points > 0 ? "+" : ""}{a.points}
                  </span>
                ))}
                <div>{s.key_drivers.join(", ")}{s.concerns.length > 0 && <span className="muted"> · weak on {s.concerns.length}</span>}</div>
              </span>
            </label>
          ))}
        </div>
      </section>

      <div className="two-col">
        <section className="card">
          <h3>Why this ranking</h3>
          {ex?.reasons?.length ? <ul className="small" style={{ margin: 0, paddingLeft: "1.1rem" }}>{ex.reasons.map((r) => <li key={r}>{r}</li>)}</ul> : null}
          {ex?.alternatives?.length ? (
            <dl className="small" style={{ margin: 0 }}>
              {ex.alternatives.map((a) => <div key={a.model}><dt><strong>{a.model}</strong></dt><dd style={{ margin: "0 0 0.4rem" }}>{a.why_not}</dd></div>)}
            </dl>
          ) : null}
          {ex?.revisit_if?.length ? <p className="note">Revisit if: {ex.revisit_if.join("; ")}</p> : null}
        </section>
        <section className="card">
          <h3>Rules that fired</h3>
          {gate.rules_fired.length === 0 ? <p className="muted small">None. The ranking comes from multi-criteria analysis alone.</p> : (
            <ul className="issues">{gate.rules_fired.map((r) => (
              <li key={r.rule} className="stripe low"><code>{r.rule}</code> {r.reason}{r.source && <div className="small muted">Source: {r.source}</div>}</li>
            ))}</ul>
          )}
          <h3>Project factors</h3>
          <div className="factor-grid">
            {factors.map(([k, v]) => (
              <div key={k} className="factor">
                <span>{k.replace(/_/g, " ")}{sources[k] === "measured" && <span className="small muted" title="Computed from project data, not estimated"> · measured</span>}</span>
                <Pips value={v} />
              </div>
            ))}
          </div>
          <p className="muted small">{String(gate.factors.rationale ?? "")}</p>
        </section>
      </div>

      {gate.characteristics && gate.characteristics.length > 0 && (
        <Characteristics items={gate.characteristics} roles={gate.required_approvers} busy={busy} onDecide={onDecide} />
      )}

      <ApproverBar required={gate.required_approvers} pending={gate.pending_approvers} approvals={gate.approvals} busy={busy}
        approveLabel={`Approve ${selected}`} onApprove={decide("approve")} onRegenerate={decide("regenerate")} />
    </div>
  );
}

/** The course's SDLC-selection questions. Approvers (usually the project manager) can answer or correct them and re-rank. */
function Characteristics({ items, roles, busy, onDecide }: {
  items: SdlcCharacteristic[]; roles: string[]; busy: boolean; onDecide: (label: string, d: Decision) => void;
}) {
  const catalog = useCatalog();
  const [edits, setEdits] = useState<Record<string, Answer>>({});
  const [reviewer, setReviewer] = useState("");
  const [role, setRole] = useState(roles.includes("project_manager") ? "project_manager" : roles[0]);
  const groups = useMemo(() => {
    const g = new Map<string, SdlcCharacteristic[]>();
    items.forEach((c) => g.set(c.category_name, [...(g.get(c.category_name) ?? []), c]));
    return [...g];
  }, [items]);
  const unknown = items.filter((c) => !c.answer).length;
  const changed = Object.entries(edits).filter(([id, a]) => (items.find((c) => c.id === id)?.answer ?? "unknown") !== a);

  function rerank() {
    onDecide("Re-ranking with the updated project characteristics…", {
      gate: "sdlc", decision: "regenerate", reviewer: reviewer.trim(), reviewer_role: role, feedback: "",
      characteristic_answers: Object.fromEntries(changed),
    });
  }

  return (
    <section className="card stack">
      <div className="section-head">
        <h3>Project characteristics <span className="small muted">· course SDLC-selection matrices</span></h3>
        <span className="small muted">{items.length - unknown}/{items.length} answered</span>
      </div>
      <p className="note">
        Each answer is compared with every model's column in the course selection matrices. Answers come from measured project
        data, the AI, or an approver; unknown ones are left out. Team questions usually need the project manager.
      </p>
      <div className="table-scroll">
        <table>
          <thead><tr><th>Question</th><th>Answer</th><th>From</th><th>Evidence</th></tr></thead>
          {groups.map(([name, qs]) => (
            <tbody key={name}>
              <tr className="group-row"><th colSpan={4}>{name}</th></tr>
              {qs.map((c) => {
                const value = edits[c.id] ?? c.answer ?? "unknown";
                return (
                  <tr key={c.id} className={edits[c.id] && edits[c.id] !== (c.answer ?? "unknown") ? "req-modified" : ""}>
                    <td className="small">{c.text}</td>
                    <td>
                      <select aria-label={c.text} value={value} onChange={(e) => setEdits({ ...edits, [c.id]: e.target.value as Answer })}>
                        <option value="yes">Yes</option><option value="no">No</option><option value="unknown">Unknown</option>
                      </select>
                    </td>
                    <td><span className={`tag ${c.source === "human" ? "accent" : c.source === "unknown" ? "" : "ok"}`}>{SOURCE_LABEL[c.source]}</span></td>
                    <td className="small muted">{c.reason || "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          ))}
        </table>
      </div>
      <div className="row">
        <label className="grow" htmlFor="char-reviewer">Your name<input id="char-reviewer" value={reviewer} onChange={(e) => setReviewer(e.target.value)} /></label>
        <label className="grow" htmlFor="char-role">Answering as<select id="char-role" value={role} onChange={(e) => setRole(e.target.value)}>
          {roles.map((r) => <option key={r} value={r}>{catalog.role[r]?.name ?? r}</option>)}</select></label>
        <button className="primary" disabled={busy || !reviewer.trim() || changed.length === 0} onClick={rerank}>
          Re-rank with {changed.length || "no"} change{changed.length === 1 ? "" : "s"}
        </button>
      </div>
      <p className="muted small">Re-ranking clears approvals already given, because the recommendation may change.</p>
    </section>
  );
}
