import { useEffect, useState } from "react";
import { api, type AuditEntry } from "../api";

export default function AuditPanel({ projectId }: { projectId: number }) {
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);

  useEffect(() => {
    api.audit(projectId).then(setEntries);
  }, [projectId]);

  if (!entries) return <p className="muted">Loading…</p>;
  return (
    <section className="card">
      <h2>Audit trail ({entries.length})</h2>
      <table>
        <thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Detail</th></tr></thead>
        <tbody>
          {entries.map((e, i) => (
            <tr key={i}>
              <td className="nowrap small">{new Date(e.at).toLocaleString()}</td>
              <td><code>{e.actor}</code></td>
              <td>{e.action.replace(/_/g, " ")}</td>
              <td><pre className="detail">{JSON.stringify(e.detail)}</pre></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
