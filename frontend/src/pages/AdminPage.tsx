import { useCallback, useEffect, useState } from "react";
import { api, type AdminUser, type Member, type Project, type RetentionPolicy } from "../api";
import { useCatalog } from "../catalog";

/** Step 17 administration: users and roles, MFA resets, project membership, legal hold, audit integrity, retention. */
export default function AdminPage() {
  const catalog = useCatalog();
  const roleIds = ["admin", ...catalog.roles.map((r) => r.id)];
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [pid, setPid] = useState<number | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [retention, setRetention] = useState<RetentionPolicy[]>([]);
  const [audit, setAudit] = useState<{ valid: boolean; checked: number; broken_at: number | null } | null>(null);
  const [prov, setProv] = useState<Record<string, unknown> | null>(null);
  const [form, setForm] = useState({ username: "", display_name: "", password: "", roles: [] as string[] });
  const [member, setMember] = useState("");
  const [holdReason, setHoldReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(() => Promise.all([
    api.adminUsers().then(setUsers), api.projects().then((p) => { setProjects(p); setPid((x) => x ?? p[0]?.id ?? null); }),
    api.retention().then(setRetention),
  ]).catch((e: Error) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (pid) api.members(pid).then(setMembers).catch((e: Error) => setError(e.message)); }, [pid]);

  async function act(fn: () => Promise<unknown>, done?: string) {
    setError(null); setNote(null);
    try { await fn(); await load(); if (pid) setMembers(await api.members(pid)); if (done) setNote(done); }
    catch (e) { setError((e as Error).message); }
  }
  const toggle = (list: string[], r: string) => (list.includes(r) ? list.filter((x) => x !== r) : [...list, r]);
  const roleName = (r: string) => (r === "admin" ? "Administrator" : catalog.role[r]?.name ?? r);

  return (
    <main className="page stack">
      <header className="page-head">
        <span className="eyebrow">Step 17 · platform security</span>
        <h1>Administration</h1>
        <p className="muted">Accounts and roles decide what each person may do; project membership isolates projects; every change is audited.</p>
      </header>
      {error && <div className="alert error">{error}</div>}
      {note && <div className="alert ok">{note}</div>}

      <section className="card stack">
        <h2>Users and roles</h2>
        <div className="table-scroll">
          <table>
            <thead><tr><th>User</th><th>Roles</th><th>MFA</th><th>Status</th><th /></tr></thead>
            <tbody>{users.map((u) => (
              <tr key={u.id}>
                <td><strong>{u.display_name}</strong><div className="small muted">{u.username}</div></td>
                <td className="small">
                  <details><summary>{u.roles.map(roleName).join(", ") || "none"}</summary>
                    <div className="role-grid">{roleIds.map((r) => (
                      <label key={r} className="check-inline"><input type="checkbox" checked={u.roles.includes(r)}
                        onChange={() => act(() => api.setRoles(u.id, toggle(u.roles, r)), `Roles of ${u.username} updated`)} />{roleName(r)}</label>
                    ))}</div>
                  </details>
                </td>
                <td>{u.mfa_enabled ? <span className="tag ok">enrolled</span> : <span className="tag sev-medium">not enrolled</span>}</td>
                <td>{!u.active ? <span className="tag sev-high">disabled</span> : u.locked ? <span className="tag sev-medium">locked</span> : <span className="tag ok">active</span>}</td>
                <td className="nowrap">
                  <button className="link" onClick={() => act(() => api.resetMfa(u.id), `MFA reset for ${u.username}; they enrol again at next sign-in`)}>Reset MFA</button>
                  <button className="link danger" onClick={() => act(() => api.setActive(u.id, !u.active))}>{u.active ? "Disable" : "Enable"}</button>
                </td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <h3>New user</h3>
        <div className="row">
          <label className="grow">Username<input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></label>
          <label className="grow">Display name<input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} /></label>
          <label className="grow">Initial password<input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
        </div>
        <div className="role-grid">{roleIds.map((r) => (
          <label key={r} className="check-inline"><input type="checkbox" checked={form.roles.includes(r)}
            onChange={() => setForm({ ...form, roles: toggle(form.roles, r) })} />{roleName(r)}</label>
        ))}</div>
        <p className="muted small">At least 12 characters with upper- and lower-case letters and a digit. The user enrols MFA at first sign-in.</p>
        <div><button className="primary" disabled={!form.username || !form.password || !form.roles.length}
          onClick={() => act(() => api.createUser(form), `Created ${form.username}`).then(() => setForm({ username: "", display_name: "", password: "", roles: [] }))}>Create user</button></div>
      </section>

      <section className="card stack">
        <h2>Project membership and legal hold</h2>
        <label>Project<select value={pid ?? ""} onChange={(e) => setPid(Number(e.target.value))}>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name} (#{p.id})</option>)}</select></label>
        <ul className="issues">{members.map((m) => (
          <li key={m.user_id}>{m.display_name} <span className="muted small">({m.username}) · added by {m.added_by}</span>
            <button className="link danger" onClick={() => pid && act(() => api.removeMember(pid, m.user_id))}>Remove</button></li>
        ))}</ul>
        <div className="row">
          <label className="grow">Add member (username)<input value={member} onChange={(e) => setMember(e.target.value)} /></label>
          <button disabled={!pid || !member.trim()} onClick={() => pid && act(() => api.addMember(pid, member.trim()), `${member} added`).then(() => setMember(""))}>Add</button>
        </div>
        <div className="row">
          <label className="grow">Legal hold reason<input value={holdReason} onChange={(e) => setHoldReason(e.target.value)} /></label>
          <button disabled={!pid || holdReason.trim().length < 3} onClick={() => pid && act(() => api.legalHold(pid, true, holdReason), "Legal hold set: this project will not be purged")}>Set hold</button>
          <button disabled={!pid || holdReason.trim().length < 3} onClick={() => pid && act(() => api.legalHold(pid, false, holdReason), "Legal hold released")}>Release</button>
          <button className="link" disabled={!pid} onClick={() => pid && act(() => api.archive(pid), "Archived: the retention period starts now")}>Archive project</button>
        </div>
      </section>

      <section className="card stack">
        <div className="section-head"><h2>Audit integrity</h2>
          <button onClick={() => act(async () => setAudit(await api.auditVerify()))}>Verify audit chain</button></div>
        {audit && (audit.valid
          ? <div className="alert ok">Hash chain intact: {audit.checked} events verified.</div>
          : <div className="alert error">Chain broken at event #{audit.broken_at}: an audit record was changed or removed.</div>)}
      </section>

      <section className="card stack">
        <div className="section-head"><h2>Data retention</h2>
          <button className="danger" onClick={() => act(async () => { const r = await api.applyRetention(); setNote(`Purged: ${JSON.stringify(r)}`); })}>Apply now</button></div>
        <table><thead><tr><th>Data</th><th>Kept for</th><th>Due now</th><th>Why</th></tr></thead>
          <tbody>{retention.map((r) => (
            <tr key={r.id}><td className="small">{r.data}</td><td className="num">{r.keep_days} days</td><td className="num">{r.due}</td><td className="small muted">{r.basis}</td></tr>
          ))}</tbody></table>
        <p className="muted small">{retention[0]?.projects_on_legal_hold ?? 0} project(s) on legal hold are never purged.</p>
      </section>

      <section className="card stack">
        <div className="section-head"><h2>Model and knowledge versions</h2>
          <button onClick={() => act(async () => setProv(await api.provenance()))}>Show current versions</button></div>
        {prov && <pre className="small provenance">{JSON.stringify(prov, null, 2)}</pre>}
      </section>
    </main>
  );
}
