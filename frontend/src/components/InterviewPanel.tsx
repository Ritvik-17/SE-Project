import { useEffect, useState } from "react";
import { api, type InterviewTemplate, type Project } from "../api";
import { useCatalog } from "../catalog";
import AiInterview from "./AiInterview";

interface Props { project: Project; onSubmitted: () => void; onSourcesChanged: () => void }

/** Stakeholder interviews: adaptive AI interviewer, or the role-specific template as a questionnaire. */
export default function InterviewPanel({ project, onSubmitted, onSourcesChanged }: Props) {
  const catalog = useCatalog();
  const [role, setRole] = useState(catalog.domain[project.domain].required_roles[0]);
  const [mode, setMode] = useState<"ai" | "template">("ai");
  const onCompleted = onSourcesChanged;
  const [template, setTemplate] = useState<InterviewTemplate | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setTemplate(null);
    setAnswers({});
    api.interviewTemplate(role, project.domain).then(setTemplate).catch((e: Error) => setError(e.message));
  }, [role, project.domain]);

  const key = (category: string, q: string) => `${category}::${q}`;
  const answered = Object.values(answers).filter((a) => a.trim()).length;

  async function submit() {
    if (!template) return;
    const payload = template.sections.flatMap((s) =>
      s.questions.map((q) => ({ category: s.category, question: q, answer: answers[key(s.category, q)] ?? "" })));
    setBusy(true);
    setError(null);
    try {
      await api.submitInterview(project.id, { stakeholder_role: role, answers: payload });
      onSubmitted();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const r = catalog.role[role];

  return (
    <div className="stack">
      <section className="card">
        <h2>Stakeholder interview</h2>
        <label>
          Interviewee role
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            {catalog.roles.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
          </select>
        </label>
        <p>{r.description}</p>
        <p className="muted small"><strong>Provides:</strong> {r.provides}</p>
        <div className="chips">
          {r.categories.primary.map((c) => <span key={c} className="chip primary">● {catalog.category[c].name}</span>)}
          {r.categories.secondary.map((c) => <span key={c} className="chip">○ {catalog.category[c].name}</span>)}
        </div>
        <div className="segmented" style={{ marginTop: "0.8rem" }}>
          <button className={mode === "ai" ? "active" : ""} onClick={() => setMode("ai")}>AI interviewer (adaptive)</button>
          <button className={mode === "template" ? "active" : ""} onClick={() => setMode("template")}>Questionnaire (template)</button>
        </div>
      </section>

      {mode === "ai" ? <AiInterview key={role} project={project} role={role} onCompleted={onCompleted} /> : <>
      {error && <div className="alert error">{error}</div>}
      {!template ? <p className="muted">Loading template…</p> : template.sections.map((s) => (
        <section key={s.category} className="card">
          <div className="section-head">
            <h3>{s.topic}</h3>
            <span className={`chip ${s.priority === "primary" ? "primary" : ""}`}>
              {catalog.category[s.category].name} · {s.priority}
            </span>
          </div>
          {s.example_requirement && <p className="muted small">Example: <em>{s.example_requirement}</em></p>}
          {s.questions.map((q) => (
            <label key={q} className="question">
              {q}
              <textarea rows={2} value={answers[key(s.category, q)] ?? ""}
                onChange={(e) => setAnswers({ ...answers, [key(s.category, q)]: e.target.value })} />
            </label>
          ))}
        </section>
      ))}

      <div className="sticky-actions">
        <span className="muted small">{answered} question(s) answered · unanswered questions are ignored</span>
        <button className="primary" disabled={busy || answered === 0} onClick={submit}>
          {busy ? "Saving…" : "Save interview as source"}
        </button>
      </div>
      </>}
    </div>
  );
}
