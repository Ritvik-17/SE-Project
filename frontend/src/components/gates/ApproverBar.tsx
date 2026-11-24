import { useEffect, useState } from "react";
import type { Approval } from "../../api";
import { useMe } from "../../auth";
import { useCatalog } from "../../catalog";

interface Props {
  required: string[];
  pending: string[];
  approvals: Approval[];
  busy: boolean;
  approveLabel: string;
  blocker?: string;
  blockerFor?: (role: string) => string | undefined;
  onApprove: (reviewer: string, role: string, feedback: string) => void;
  onRegenerate: (reviewer: string, role: string, feedback: string) => void;
}

/** Shows who must sign off (routed by the human-approval agent) and collects one approver's decision. */
export default function ApproverBar({ required, pending, approvals, busy, approveLabel, blocker: fixedBlocker, blockerFor, onApprove, onRegenerate }: Props) {
  const catalog = useCatalog();
  const { me } = useMe();
  const mine = (r: string) => me.roles.includes(r);
  const [role, setRole] = useState(pending.find(mine) ?? pending[0] ?? required[0]);
  const reviewer = me.username;  // decisions are recorded under the signed-in account
  const [feedback, setFeedback] = useState("");

  useEffect(() => {
    if (!pending.includes(role)) setRole(pending.find((r) => me.roles.includes(r)) ?? pending[0] ?? required[0]);
  }, [pending, required, role, me.roles]);
  const blocker = fixedBlocker ?? blockerFor?.(role);

  const signed = new Map(approvals.filter((a) => a.decision === "approve").map((a) => [a.role, a]));

  return (
    <section className="card stack approver-bar">
      <h2>Required approvals</h2>
      <div className="chips">
        {required.map((r) => (
          <span key={r} className={`chip ${signed.has(r) ? "ok" : "missing"}`}>
            {signed.has(r) ? `${catalog.role[r].name} · signed by ${signed.get(r)!.reviewer}` : `${catalog.role[r].name} · pending`}
          </span>
        ))}
      </div>
      <p className="note">
        Routing is decided by the human-approval agent from the content under review. You can only act in roles your account holds; the decision is recorded under your name.
      </p>
      <div className="row">
        <label className="grow">
          Approving as
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            {required.map((r) => (
              <option key={r} value={r} disabled={!pending.includes(r) || !mine(r)}>
                {catalog.role[r].name}{!pending.includes(r) ? " (signed)" : !mine(r) ? " (not your role)" : ""}
              </option>
            ))}
          </select>
        </label>
        <div className="grow small muted">Signed in as <strong>{me.display_name}</strong> ({me.username})</div>
      </div>
      <label>
        Feedback / comments <span className="muted small">(required to regenerate)</span>
        <textarea rows={2} value={feedback} onChange={(e) => setFeedback(e.target.value)} />
      </label>
      <div className="row">
        <button className="primary" disabled={busy || !!blocker || !pending.includes(role) || !mine(role)} title={blocker}
          onClick={() => { onApprove(reviewer.trim(), role, feedback); setFeedback(""); }}>
          {approveLabel}
        </button>
        {blocker && <span className="small warn-text">{blocker}</span>}
        <button disabled={busy || !reviewer.trim() || !feedback.trim()}
          onClick={() => { onRegenerate(reviewer.trim(), role, feedback); setFeedback(""); }}>
          Request regeneration
        </button>
      </div>
    </section>
  );
}
