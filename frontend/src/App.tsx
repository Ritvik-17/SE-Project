import { lazy, Suspense, useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { api, type Health } from "./api";
import { useMe } from "./auth";
import AdminPage from "./pages/AdminPage";
import KnowledgePage from "./pages/KnowledgePage";
import OperationsPage from "./pages/OperationsPage";
import ProjectPage from "./pages/ProjectPage";
import ProjectsPage from "./pages/ProjectsPage";
import ScopePage from "./pages/ScopePage";

const OPS_ROLES = ["admin", "auditor_regulator", "project_manager", "compliance_legal"];

// Mermaid is large; load the graph page only when visited.
const AgentsPage = lazy(() => import("./pages/AgentsPage"));

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const { me, signOut } = useMe();
  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  return (
    <div className="shell">
      <aside className="rail">
        <NavLink to="/" className="wordmark" end>
          <span className="wordmark-mark" aria-hidden="true">RE</span>
          <span>Requirements Desk</span>
        </NavLink>
        <nav aria-label="Main">
          <NavLink to="/" end>Projects</NavLink>
          <NavLink to="/knowledge">Knowledge base</NavLink>
          <NavLink to="/scope">System scope</NavLink>
          <NavLink to="/agents">Agent graph</NavLink>
          {OPS_ROLES.some((r) => me.roles.includes(r)) && <NavLink to="/operations">Deployment &amp; monitoring</NavLink>}
          {me.roles.includes("admin") && <NavLink to="/admin">Administration</NavLink>}
        </nav>
        <div className="rail-foot">
          <span className="eyebrow">Signed in</span>
          <span className="status-line" title={me.roles.join(", ")}><span className="dot ok" />{me.display_name}</span>
          <button className="link signout" onClick={signOut}>Sign out</button>
          <span className="eyebrow">System</span>
          {health ? (
            <>
              <span className="status-line"><span className="dot ok" />Database connected</span>
              <span className="status-line">
                <span className={`dot ${health.llm_configured ? "ok" : "warn"}`} />
                {health.llm_configured ? <>Model <code>{health.model}</code></> : "OpenAI key missing"}
              </span>
            </>
          ) : <span className="status-line"><span className="dot warn" />API unreachable</span>}
        </div>
      </aside>
      <div className="main">
        <Routes>
          <Route path="/" element={<ProjectsPage />} />
          <Route path="/knowledge" element={<KnowledgePage />} />
          <Route path="/scope" element={<ScopePage />} />
          <Route path="/agents" element={<Suspense fallback={<div className="page muted">Loading graph…</div>}><AgentsPage /></Suspense>} />
          <Route path="/projects/:id" element={<ProjectPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/operations" element={<OperationsPage />} />
        </Routes>
      </div>
    </div>
  );
}
